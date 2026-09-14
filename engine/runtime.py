import os
import sys
import shutil
import tempfile
import subprocess
from engine.layer import extract_layer

def assemble_rootfs(layers: list[dict], tmp_dir: str):
    """Extract all layers in order into tmp_dir."""
    for layer in layers:
        extract_layer(layer["digest"], tmp_dir)


def run_container(manifest: dict, cmd_override: list = None, env_overrides: dict = None):
    """
    Assemble filesystem, isolate process, run command, cleanup.
    """
    config = manifest.get("config", {})
    cmd = cmd_override or config.get("Cmd")
    if not cmd:
        print("Error: No CMD defined and no command provided.", file=sys.stderr)
        sys.exit(1)

    workdir = config.get("WorkingDir") or "/"

    # Build environment
    env = {}
    for item in config.get("Env", []):
        k, _, v = item.partition("=")
        env[k] = v
    if env_overrides:
        env.update(env_overrides)

    # Assemble rootfs in temp dir
    tmp_dir = tempfile.mkdtemp(prefix="docksmith_run_")
    try:
        assemble_rootfs(manifest["layers"], tmp_dir)
        _run_isolated(tmp_dir, cmd, workdir, env)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_in_build(layers: list[dict], cmd: list, workdir: str, env: dict):
    """
    Same isolation used during RUN build steps.
    Returns (exit_code).
    """
    tmp_dir = tempfile.mkdtemp(prefix="docksmith_build_")
    try:
        assemble_rootfs(layers, tmp_dir)
        return _run_isolated(tmp_dir, cmd, workdir, env)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_isolated(rootfs: str, cmd: list, workdir: str, env: dict):
    """
    Run cmd inside rootfs using unshare + chroot for isolation.
    Requires root or user namespaces.
    """
    # Build the full command using unshare for namespace isolation
    full_cmd = [
        "unshare",
        "--mount",
        "--uts",
        "--ipc",
        "--pid",
        "--fork",
        "--mount-proc",
        "chroot",
        rootfs,
        "/bin/sh", "-c",
        " ".join(cmd) if isinstance(cmd, list) else cmd
    ]

    # Build env for subprocess
    proc_env = dict(os.environ)
    proc_env.update(env)

    # Set working directory inside chroot
    # We can't use cwd directly since it's inside chroot,
    # so we prepend cd to the command
    if workdir and workdir != "/":
        shell_cmd = f"cd {workdir} && " + (" ".join(cmd) if isinstance(cmd, list) else cmd)
        full_cmd = [
            "unshare",
            "--mount",
            "--uts",
            "--ipc",
            "--pid",
            "--fork",
            "--mount-proc",
            "chroot",
            rootfs,
            "/bin/sh", "-c",
            shell_cmd
        ]

    result = subprocess.run(full_cmd, env=proc_env)
    return result.returncode
