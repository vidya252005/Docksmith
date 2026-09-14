#!/bin/bash
# Downloads Alpine 3.18 rootfs and imports it into docksmith local store

set -e

DOCKSMITH_DIR="$HOME/.docksmith"
IMAGES_DIR="$DOCKSMITH_DIR/images"
LAYERS_DIR="$DOCKSMITH_DIR/layers"

mkdir -p "$IMAGES_DIR" "$LAYERS_DIR"

echo "Downloading Alpine 3.18 minimal rootfs..."
ALPINE_URL="https://dl-cdn.alpinelinux.org/alpine/v3.18/releases/x86_64/alpine-minirootfs-3.18.0-x86_64.tar.gz"
TMP_TAR="/tmp/alpine-base.tar.gz"

wget -q --show-progress "$ALPINE_URL" -O "$TMP_TAR"

echo "Importing into docksmith..."

# Compute sha256 of the tar
DIGEST=$(sha256sum "$TMP_TAR" | awk '{print $1}')
LAYER_FILE="$LAYERS_DIR/${DIGEST}.tar"

# Copy as layer (decompress first)
echo "Extracting and recompressing as uncompressed tar..."
TMP_DIR=$(mktemp -d)
tar -xzf "$TMP_TAR" -C "$TMP_DIR"

# Repack as uncompressed tar with sorted entries and zeroed timestamps
python3 - <<EOF
import tarfile, os, io

src = "$TMP_DIR"
out = "$LAYER_FILE"

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as tar:
    entries = []
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for fname in sorted(files):
            full = os.path.join(root, fname)
            arc = os.path.relpath(full, src)
            entries.append((full, arc))
    for full, arc in sorted(entries, key=lambda x: x[1]):
        try:
            info = tar.gettarinfo(full, arcname=arc)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with open(full, "rb") as f:
                tar.addfile(info, f)
        except (FileNotFoundError, PermissionError):
            pass

with open(out, "wb") as f:
    f.write(buf.getvalue())

import hashlib
digest = hashlib.sha256(buf.getvalue()).hexdigest()
print(f"Layer digest: sha256:{digest}")
EOF

# Get actual digest of saved file
ACTUAL_DIGEST=$(sha256sum "$LAYER_FILE" | awk '{print $1}')
FINAL_LAYER="$LAYERS_DIR/${ACTUAL_DIGEST}.tar"
mv "$LAYER_FILE" "$FINAL_LAYER"

SIZE=$(wc -c < "$FINAL_LAYER")

# Write manifest
python3 - <<EOF
import json, hashlib, os
from datetime import datetime, timezone

manifest = {
    "name": "alpine",
    "tag": "3.18",
    "digest": "",
    "created": datetime.now(timezone.utc).isoformat(),
    "config": {
        "Env": [],
        "Cmd": ["/bin/sh"],
        "WorkingDir": "/"
    },
    "layers": [
        {
            "digest": "sha256:${ACTUAL_DIGEST}",
            "size": ${SIZE},
            "createdBy": "alpine base layer"
        }
    ]
}

temp = dict(manifest)
temp["digest"] = ""
canonical = json.dumps(temp, sort_keys=True, separators=(",", ":"))
digest = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
manifest["digest"] = digest

out = os.path.expanduser("~/.docksmith/images/alpine_3.18.json")
with open(out, "w") as f:
    json.dump(manifest, f, indent=2)

print(f"Image manifest saved: alpine:3.18 ({digest[:19]})")
EOF

rm -rf "$TMP_DIR" "$TMP_TAR"
echo "Done! Alpine 3.18 is ready."   
