# DOCKSMITH
A Docker-like build and runtime system built from scratch in Python.

## 1. Overview
Docksmith is a simplified containerization tool designed to demonstrate three core systems programming concepts:
- **Build Caching**: How deterministic cache keys and invalidation semantics work.
- **Content-Addressable Storage**: Storing image layers as immutable, SHA-256 named tar archives.
- **Process Isolation**: Achieving OS-level isolation using Linux namespaces (`unshare`) and `chroot`.

The system operates as a single CLI binary with no background daemon process. All state is stored on disk under `~/.docksmith/`.

## 2. Project Structure
- `docksmith.py`: The main CLI entry point that handles user commands.
- `engine/`:
    - `builder.py`: Parses the Docksmithfile and manages the build state.
    - `runtime.py`: Assembles the rootfs and executes the isolated process.
    - `layer.py`: Creates reproducible, content-addressed tar archives.
    - `cache.py`: Computes deterministic cache keys for build steps.
    - `image.py`: Manages image manifests and local storage operations.
- `sample/`: Contains a sample application (`app.py` and `Docksmithfile`).
- `import_base.sh`: Script to import base images for fully offline operation.

## 3. Supported Instructions
The build system supports the following six instructions:
- `FROM`: Loads a base image from the local store.
- `COPY`: Copies files from the build context into the image.
- `RUN`: Executes a command inside the isolated image filesystem.
- `WORKDIR`: Sets the working directory for subsequent steps.
- `ENV`: Defines environment variables in the image config.
- `CMD`: Sets the default execution command for the container.

## 4. Getting Started
### Prerequisites
- **Linux OS**: Required for namespace primitives (unshare/chroot).
- **Python 3.x**: Core implementation language.
- **Sudo Privileges**: Necessary for process isolation commands.

### Usage
1. **Import Base Image**:
   ```bash
   chmod +x import_base.sh
   ./import_base.sh
2. **Build an Image**:
   ```bash
   python3 docksmith.py build -t myapp:latest ./sample
2. **Run a Container**:
   ```bash
   python3 docksmith.py run myapp:latest

## 5. Key Constraints
- **Offline Only**: No network access is permitted during build or run operations.
- **No Existing Runtimes**: Isolation is implemented directly using OS primitives, not Docker or runc.
- **Verified Isolation**: Files created inside a container will not appear on the host filesystem.
# Docksmith
