import os
import sys
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone

from engine.image import (
    load_image, save_image, make_manifest,
    LAYERS_DIR, IMAGES_DIR
)
from engine.layer import (
    create_layer_tar, save_layer, glob_files, compute_file_hash,
    create_layer_tar_from_dir
)
from engine.cache import compute_cache_key, check_cache, store_cache
from engine.runtime import run_in_build, assemble_rootfs


def parse_docksmithfile(context_dir):
    path = os.path.join(context_dir, "Docksmithfile")
    if not os.path.exists(path):
        print(f"Error: Docksmithfile not found in {context_dir}", file=sys.stderr)
        sys.exit(1)

    instructions = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            instruction = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""
            valid = {"FROM", "COPY", "RUN", "WORKDIR", "ENV", "CMD"}
            if instruction not in valid:
                print(f"Error: Unknown instruction '{instruction}' at line {lineno}", file=sys.stderr)
                sys.exit(1)
            instructions.append((instruction, args, lineno))
    return instructions


def build(context_dir, name, tag, no_cache=False):
    instructions = parse_docksmithfile(context_dir)
    total_steps = len(instructions)

    # State
    base_manifest = None
    layers = []
    config = {"Env": [], "Cmd": None, "WorkingDir": ""}
    workdir = ""
    env_state = {}
    prev_digest = None
    cache_busted = False
    original_created = None

    step = 0
    total_time = 0.0

    for instruction, args, lineno in instructions:
        step += 1

        if instruction == "FROM":
            print(f"Step {step}/{total_steps} : FROM {args}")
            parts = args.split(":")
            img_name = parts[0]
            img_tag = parts[1] if len(parts) > 1 else "latest"
            try:
                base_manifest = load_image(img_name, img_tag)
            except FileNotFoundError:
                print(f"Error: Base image '{args}' not found in local store.", file=sys.stderr)
                sys.exit(1)
            layers = list(base_manifest.get("layers", []))
            base_cfg = base_manifest.get("config", {})
            config["Env"] = list(base_cfg.get("Env", []))
            config["WorkingDir"] = base_cfg.get("WorkingDir", "")
            workdir = config["WorkingDir"]
            # Re-parse env_state from base
            for item in config["Env"]:
                k, _, v = item.partition("=")
                env_state[k] = v
            prev_digest = base_manifest["digest"]

        elif instruction == "WORKDIR":
            workdir = args
            config["WorkingDir"] = workdir

        elif instruction == "ENV":
            # Support KEY=VALUE format
            k, _, v = args.partition("=")
            env_state[k.strip()] = v.strip()
            config["Env"] = [f"{k}={v}" for k, v in sorted(env_state.items())]

        elif instruction == "CMD":
            try:
                config["Cmd"] = json.loads(args)
            except json.JSONDecodeError:
                print(f"Error: CMD must be a JSON array at line {lineno}", file=sys.stderr)
                sys.exit(1)

        elif instruction == "COPY":
            start = time.time()
            src_pattern, dest = args.split(None, 1)

            # Gather source files
            matched = glob_files(context_dir, src_pattern)
            if not matched:
                print(f"Error: COPY found no files matching '{src_pattern}'", file=sys.stderr)
                sys.exit(1)

            # Compute file hashes for cache key
            copy_hashes = {}
            for fpath in matched:
                rel = os.path.relpath(fpath, context_dir)
                copy_hashes[rel] = compute_file_hash(fpath)

            cache_key = compute_cache_key(
                prev_digest, f"COPY {args}", workdir, env_state, copy_hashes
            ) if not no_cache else None

            # Check cache
            cached_digest = None
            if not no_cache and not cache_busted:
                cached_digest = check_cache(cache_key)

            if cached_digest:
                elapsed = time.time() - start
                print(f"Step {step}/{total_steps} : COPY {args} [CACHE HIT] {elapsed:.2f}s")
                layers.append({
                    "digest": cached_digest,
                    "size": os.path.getsize(
                        os.path.join(LAYERS_DIR, cached_digest.replace("sha256:", "") + ".tar")
                    ),
                    "createdBy": f"COPY {args}"
                })
                prev_digest = cached_digest
            else:
                # Build tar of copied files
                files_to_tar = []
                for fpath in matched:
                    fname = os.path.basename(fpath)
                    files_to_tar.append((fpath, os.path.join(dest, fname)))

                # Handle WORKDIR creation
                if workdir:
                    _ensure_workdir_in_tar(files_to_tar, workdir)

                tar_bytes = create_layer_tar(files_to_tar)
                digest = save_layer(tar_bytes)

                if not no_cache:
                    store_cache(cache_key, digest)
                    cache_busted = True

                elapsed = time.time() - start
                print(f"Step {step}/{total_steps} : COPY {args} [CACHE MISS] {elapsed:.2f}s")
                layers.append({
                    "digest": digest,
                    "size": len(tar_bytes),
                    "createdBy": f"COPY {args}"
                })
                prev_digest = digest

        elif instruction == "RUN":
            start = time.time()

            cache_key = compute_cache_key(
                prev_digest, f"RUN {args}", workdir, env_state
            ) if not no_cache else None

            cached_digest = None
            if not no_cache and not cache_busted:
                cached_digest = check_cache(cache_key)

            if cached_digest:
                elapsed = time.time() - start
                print(f"Step {step}/{total_steps} : RUN {args} [CACHE HIT] {elapsed:.2f}s")
                layers.append({
                    "digest": cached_digest,
                    "size": os.path.getsize(
                        os.path.join(LAYERS_DIR, cached_digest.replace("sha256:", "") + ".tar")
                    ),
                    "createdBy": f"RUN {args}"
                })
                prev_digest = cached_digest
            else:
                # Execute RUN in isolation
                tmp_dir = tempfile.mkdtemp(prefix="docksmith_run_")
                try:
                    assemble_rootfs(layers, tmp_dir)

                    # Ensure workdir exists
                    if workdir:
                        os.makedirs(os.path.join(tmp_dir, workdir.lstrip("/")), exist_ok=True)

                    # Build env for the command
                    run_env = dict(env_state)

                    exit_code = run_in_build(layers, ["/bin/sh", "-c", args], workdir, run_env)
                    if exit_code != 0:
                        print(f"Error: RUN command failed with exit code {exit_code}", file=sys.stderr)
                        sys.exit(1)

                    # Capture delta: diff tmp_dir before/after
                    # For simplicity, tar the entire rootfs as delta
                    tar_bytes = _tar_rootfs(tmp_dir)
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

                digest = save_layer(tar_bytes)

                if not no_cache:
                    store_cache(cache_key, digest)
                    cache_busted = True

                elapsed = time.time() - start
                print(f"Step {step}/{total_steps} : RUN {args} [CACHE MISS] {elapsed:.2f}s")
                layers.append({
                    "digest": digest,
                    "size": len(tar_bytes),
                    "createdBy": f"RUN {args}"
                })
                prev_digest = digest

    # Save manifest
    manifest = make_manifest(name, tag, layers, config, created=original_created)
    digest = save_image(manifest)
    print(f"\nSuccessfully built {digest[:19]} {name}:{tag} ({total_time:.2f}s)")
    return manifest


def _ensure_workdir_in_tar(files_to_tar, workdir):
    """Ensure workdir path exists as a directory entry in the tar."""
    pass  # handled by makedirs during extraction


def _tar_rootfs(rootfs_dir):
    """Tar entire rootfs directory for RUN layer delta."""
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for root, dirs, files in os.walk(rootfs_dir):
            dirs.sort()
            for fname in sorted(files):
                full_path = os.path.join(root, fname)
                arcname = os.path.relpath(full_path, rootfs_dir)
                try:
                    info = tar.gettarinfo(full_path, arcname=arcname)
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    with open(full_path, "rb") as f:
                        tar.addfile(info, f)
                except (FileNotFoundError, PermissionError):
                    pass
    return buf.getvalue()
