import json
import os
import hashlib
from datetime import datetime, timezone

DOCKSMITH_DIR = os.path.expanduser("~/.docksmith")
IMAGES_DIR = os.path.join(DOCKSMITH_DIR, "images")
LAYERS_DIR = os.path.join(DOCKSMITH_DIR, "layers")
CACHE_DIR = os.path.join(DOCKSMITH_DIR, "cache")


def init_dirs():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(LAYERS_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)


def image_path(name, tag):
    return os.path.join(IMAGES_DIR, f"{name}_{tag}.json")


def load_image(name, tag):
    path = image_path(name, tag)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Image not found: {name}:{tag}")
    with open(path, "r") as f:
        return json.load(f)


def save_image(manifest):
    init_dirs()
    name = manifest["name"]
    tag = manifest["tag"]

    # Compute digest: serialize with digest="" then hash
    temp = dict(manifest)
    temp["digest"] = ""
    canonical = json.dumps(temp, sort_keys=True, separators=(",", ":"))
    digest = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    manifest["digest"] = digest

    path = image_path(name, tag)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)

    return digest


def list_images():
    init_dirs()
    images = []
    for fname in os.listdir(IMAGES_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(IMAGES_DIR, fname)) as f:
                images.append(json.load(f))
    return images


def delete_image(name, tag):
    path = image_path(name, tag)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Image not found: {name}:{tag}")

    with open(path) as f:
        manifest = json.load(f)

    # Delete all layer files belonging to this image
    for layer in manifest.get("layers", []):
        digest = layer["digest"]
        layer_file = os.path.join(LAYERS_DIR, digest.replace("sha256:", "") + ".tar")
        if os.path.exists(layer_file):
            os.remove(layer_file)

    os.remove(path)


def make_manifest(name, tag, layers, config, created=None):
    return {
        "name": name,
        "tag": tag,
        "digest": "",
        "created": created or datetime.now(timezone.utc).isoformat(),
        "config": config,
        "layers": layers,
    }
