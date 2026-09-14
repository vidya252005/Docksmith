import os
import tarfile
import hashlib
import fnmatch
from pathlib import Path

DOCKSMITH_DIR = os.path.expanduser("~/.docksmith")
LAYERS_DIR = os.path.join(DOCKSMITH_DIR, "layers")


def compute_file_hash(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_bytes_hash(data: bytes):
    return hashlib.sha256(data).hexdigest()


def create_layer_tar(files: list[tuple[str, str]], base_dir: str = None) -> bytes:
    """
    files: list of (src_path, dest_path_in_tar)
    Returns raw tar bytes with sorted entries and zeroed timestamps.
    """
    import io
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        # Sort by destination path for reproducibility
        for src, dest in sorted(files, key=lambda x: x[1]):
            info = tar.gettarinfo(src, arcname=dest.lstrip("/"))
            # Zero out timestamps for reproducibility
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with open(src, "rb") as f:
                tar.addfile(info, f)
    return buf.getvalue()


def create_layer_tar_from_dir(src_dir: str, dest_prefix: str) -> bytes:
    """Create a tar layer from an entire directory."""
    import io
    buf = io.BytesIO()
    files = []
    for root, dirs, filenames in os.walk(src_dir):
        dirs.sort()  # sorted for reproducibility
        for fname in sorted(filenames):
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, src_dir)
            dest = os.path.join(dest_prefix, rel_path)
            files.append((full_path, dest))

    with tarfile.open(fileobj=buf, mode="w") as tar:
        for src, dest in files:
            info = tar.gettarinfo(src, arcname=dest.lstrip("/"))
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with open(src, "rb") as f:
                tar.addfile(info, f)
    return buf.getvalue()


def save_layer(tar_bytes: bytes) -> str:
    """Save tar bytes to layers dir, return digest."""
    os.makedirs(LAYERS_DIR, exist_ok=True)
    digest = compute_bytes_hash(tar_bytes)
    layer_path = os.path.join(LAYERS_DIR, digest + ".tar")
    if not os.path.exists(layer_path):
        with open(layer_path, "wb") as f:
            f.write(tar_bytes)
    return "sha256:" + digest


def extract_layer(digest: str, target_dir: str):
    """Extract a layer tar into target_dir."""
    layer_file = os.path.join(LAYERS_DIR, digest.replace("sha256:", "") + ".tar")
    if not os.path.exists(layer_file):
        raise FileNotFoundError(f"Layer file missing: {digest}")
    with tarfile.open(layer_file, "r") as tar:
        tar.extractall(target_dir)


def glob_files(context_dir: str, pattern: str) -> list[str]:
    """Return sorted list of files matching glob pattern in context_dir."""
    matched = []
    for root, dirs, files in os.walk(context_dir):
        dirs.sort()
        for fname in sorted(files):
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, context_dir)
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(fname, pattern):
                matched.append(full)
    return sorted(matched)
