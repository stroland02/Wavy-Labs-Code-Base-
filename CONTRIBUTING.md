# Contributing to Wavy Labs

Thank you for your interest in contributing! This document covers the
development workflow for both the C++/Qt6 desktop app and the Python AI backend.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Repository Layout](#repository-layout)
4. [C++ / Qt6 Development](#c--qt6-development)
5. [Python AI Backend](#python-ai-backend)
6. [Commit & PR Guidelines](#commit--pr-guidelines)
7. [License](#license)

---

## Code of Conduct

Be respectful. Harassment, discrimination, or abusive language will not be
tolerated. We follow the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

---

## Getting Started

### Prerequisites

| Tool | Minimum version |
|------|----------------|
| Git | 2.40 |
| CMake | 3.22 |
| Ninja | 1.11 |
| Qt6 | 6.6.x (Core, Widgets, Gui, Network, WebEngineWidgets, Svg, Sql) |
| Python | 3.10+ |
| ZeroMQ | 4.x |

### Clone & bootstrap

```bash
git clone https://github.com/wavy-labs/wavy.git
cd wavy
git submodule update --init --recursive   # lmms-core, cppzmq, json
cd vendor && bash bootstrap.sh            # pip install + clone AI models
```

### Build (quick start)

```bash
# Linux / macOS
./build.sh Release

# Windows (cmd)
build.bat Release
```

The resulting binary is `build/wavy-labs` (or `build/wavy-labs.exe` on Windows).

---

## Repository Layout

```
wavy/
├── lmms-core/          ← LMMS submodule (GPL-2.0)
├── wavy-ui/            ← C++/Qt6 panel library (static)
│   ├── IPC/            ← ZeroMQ JSON-RPC client
│   ├── AIPanel/        ← Generate / Vocal / Mix tabs
│   ├── StemSplitter/
│   ├── PromptBar/
│   ├── CodeToMusic/
│   ├── ModelManager/
│   ├── LicenseGate/
│   └── Dialogs/
├── wavy-ai/            ← Python AI backend (ZeroMQ REP server)
│   ├── models/         ← Per-model wrappers
│   └── tests/          ← pytest suite
├── wavy-license-server/← FastAPI license & payment server
├── wavy-installer/     ← NSIS / DMG / AppImage builders
├── data/               ← QSS theme, icons, Qt resources
├── vendor/             ← Header-only C++ libs (cppzmq, nlohmann/json)
└── src/                ← main.cpp (dev harness)
```

---

## C++ / Qt6 Development

### Style

- C++20 standard, snake_case for variables/functions, PascalCase for classes.
- `#pragma once` in all headers.
- Prefer Qt containers (`QList`, `QMap`) inside Qt-facing code; use STL in
  pure-logic helpers.
- All user-visible strings wrapped in `tr()` for future i18n.

### Adding a new UI panel

1. Create `wavy-ui/MyPanel/MyPanel.{h,cpp}`.
2. Add both files to `WAVY_UI_SOURCES` / `WAVY_UI_HEADERS` in
   `wavy-ui/CMakeLists.txt`.
3. Wire the panel into `lmms-core/src/gui/MainWindow.wavy.patch` if it needs
   to appear in the main window.

### IPC (new RPC method)

1. Add a handler function in `wavy-ai/rpc_handlers.py`.
2. Register it in the `RPC_HANDLERS` dict.
3. Add the matching convenience wrapper in `wavy-ui/IPC/AIClient.h/.cpp`.

### Running C++ tests

C++ unit tests use Qt Test and live in `wavy-ui/tests/` (not yet scaffolded —
contributions welcome). Build them with:

```bash
cmake --build build --target wavy_ui_tests
ctest --test-dir build -V
```

---

## Python AI Backend

### Setup

```bash
cd wavy-ai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Running the server

```bash
python server.py --skip-model-check --log-level DEBUG
```

### Running tests

```bash
pytest tests/ -v
```

The test suite spins up a real ZeroMQ server on port 15555 and mocks all model
inference calls — no GPU required.

### Adding a new model

1. Create `wavy-ai/models/my_model.py` subclassing `BaseModel`.
2. Implement `load()`, `unload()`, and your inference method.
3. Add an entry to `MODEL_CATALOG` in `models/registry.py`.
4. Add a first-run download entry to `MODEL_MANIFEST` in `model_check.py`.
5. Write tests in `tests/test_my_model.py`.

---

## Commit & PR Guidelines

- **Branch naming**: `feat/short-description`, `fix/issue-42`,
  `chore/update-deps`.
- **Commit messages**: imperative mood, ≤72 chars subject line.
  Body explains *why*, not *what*.

  ```
  feat(stem-splitter): add 6-stem Demucs support

  Demucs htdemucs_6s separates vocals, bass, drums, guitar, piano, and
  other stems. Gated to Pro tier via LicenseManager::canSplitStems6().
  ```

- **PR checklist** (CI enforces these):
  - [ ] `pytest tests/ -v` passes
  - [ ] C++ builds without warnings on all three platforms
  - [ ] No new GPL code inside `wavy-ui/` (keep AI backend process-separate)
  - [ ] New public APIs documented in header comments

- **Changelog**: update the `[Unreleased]` section in `CHANGELOG.md` (will be
  created at first release).

---

## License

By contributing, you agree your changes are licensed under **GPL-2.0** for
`lmms-core/` derivatives, and **MIT** for all other Wavy Labs source code
(`wavy-ui/`, `wavy-ai/`, `wavy-license-server/`).

See [LICENSE](LICENSE) for details.
