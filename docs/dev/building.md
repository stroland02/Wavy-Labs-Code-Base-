# Building from Source

## Prerequisites

=== "Windows"

    - Visual Studio 2022 (MSVC 17) or MinGW-w64 13+
    - CMake 3.26+
    - Ninja build system
    - Qt 6.7+ (via [Qt Online Installer](https://www.qt.io/download) or `winget install Qt.Qt.6.7`)
    - Git 2.40+

=== "macOS"

    - Xcode 15+ (provides Clang 17+)
    - CMake 3.26+ (`brew install cmake`)
    - Ninja (`brew install ninja`)
    - Qt 6.7+ (`brew install qt`)

=== "Linux"

    ```bash
    # Ubuntu 22.04+
    sudo apt install build-essential cmake ninja-build git \
         qt6-base-dev qt6-tools-dev qt6-svg-dev \
         libzmq3-dev pkg-config
    ```

## Clone

```bash
git clone --recurse-submodules https://github.com/wavy-labs/wavy-labs.git
cd wavy-labs
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

## Bootstrap Vendor Libraries

```bash
# Linux / macOS
bash vendor/bootstrap.sh

# Windows (Command Prompt)
vendor\bootstrap.bat
```

This fetches the header-only cppzmq and nlohmann/json submodules.

## Build (C++)

```bash
# Linux / macOS
./build.sh Release

# Windows
build.bat Release
```

Or manually:

```bash
cmake -S . -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DWANT_QT6=ON \
      -DWAVY_LICENSE_HMAC_SECRET=changeme

cmake --build build --parallel
```

## Python Backend

```bash
cd wavy-ai

# Create virtualenv (recommended)
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# For CUDA acceleration
pip install -e ".[cuda]"

# Run the backend
python server.py
```

## Running Tests

```bash
# Python tests
cd wavy-ai
pytest tests/ -v

# C++ — build in Debug and run CTest (placeholder, tests coming in v0.3)
cmake -S . -B build-debug -DCMAKE_BUILD_TYPE=Debug
cmake --build build-debug
ctest --test-dir build-debug
```

## CMake Options

| Option | Default | Description |
|--------|---------|-------------|
| `WANT_QT6` | `ON` | Use Qt6 (required) |
| `WAVY_LICENSE_HMAC_SECRET` | `"dev"` | HMAC secret for license key validation |
| `WAVY_LICENSE_SERVER_URL` | `"https://license.wavylabs.io"` | License server base URL |
| `WAVY_USE_KEYCHAIN` | `OFF` | Store license key in OS credential store |

## Apply LMMS Patches

The `lmms-core/` submodule patches are not applied automatically.
After initializing the submodule:

```bash
cd lmms-core
git apply ../lmms-core/src/gui/MainWindow.wavy.patch
git apply ../lmms-core/src/core/Song.wavy.patch
git apply ../lmms-core/src/gui/SampleTrack.wavy.patch
git apply ../lmms-core/src/gui/FxMixerView.wavy.patch
```

Then rebuild.
