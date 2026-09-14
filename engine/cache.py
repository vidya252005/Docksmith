import os
import json
import hashlib

DOCKSMITH_DIR = os.path.expanduser("~/.docksmith")
CACHE_DIR = os.path.join(DOCKSMITH_DIR, "cache")
CACHE_INDEX = os.path.join(CACHE_DIR, "index.json")
LAYERS_DIR = os.path.join(DOCKSMITH_DIR, "layers")


def load_index():
    if not os.path.exists(CACHE_INDEX):
        return {}
    with open(CACHE_INDEX) as f:
        return json.load(f)


def save_index(index):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_INDEX, "w") as f:
        json.dump(index, f, indent=2)


def compute_cache_key(prev_digest, instruction, workdir, env_state, copy_hashes=None):
    """
    Compute a deterministic cache key.
    - prev_digest: digest of previous layer or base image manifest digest
    - instruction: full instruction text e.g. "RUN pip install flask"
    - workdir: current WORKDIR value (empty string if not set)
    - env_state: dict of all ENV vars accumulated so far
    - copy_hashes: for COPY only — dict of {filepath: sha256}
    """
    h = hashlib.sha256()

    h.update(prev_digest.encode())
    h.update(instruction.encode())
    h.update(workdir.encode())

    # ENV: sorted by key for determinism
    env_str = "&".join(f"{k}={v}" for k, v in sorted(env_state.items()))
    h.update(env_str.encode())

    # COPY: sorted by path for determinism
    if copy_hashes:
        for path in sorted(copy_hashes.keys()):
            h.update(path.encode())
            h.update(copy_hashes[path].encode())

    return h.hexdigest()


def check_cache(cache_key):
    """
    Returns layer digest if cache hit and layer file exists, else None.
    """
    index = load_index()
    if cache_key not in index:
        return None
    digest = index[cache_key]
    layer_file = os.path.join(LAYERS_DIR, digest.replace("sha256:", "") + ".tar")
    if not os.path.exists(layer_file):
        return None
    return digest


def store_cache(cache_key, layer_digest):
    index = load_index()
    index[cache_key] = layer_digest
    save_index(index)
