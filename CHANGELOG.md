# Changelog

All notable changes to Wavy Labs are documented here.
This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

---

## [0.4.0] — 2026-03-03

### Added
- **Full LMMS core integration** — `wavy-labs.exe` now launches the complete
  LMMS `GuiApplication` (MainWindow + Song Editor + Mixer + Piano Roll + all MDI
  sub-windows) with all Wavy AI panels embedded; `src/main.cpp` rewritten with
  `#ifdef WAVY_LMMS_CORE` dispatch
- **Stem Splitter right-click menu** — right-click any SampleClip in the Song
  Editor → "Wavy Labs AI" → 2-stem / 4-stem / 6-stem (Pro); applied via
  `SampleClipView::constructContextMenu()` using correct modern LMMS API
  (`SampleClip::sampleFile()`, `Song::addTrackFromAI()`)
- **CMake link fixes for integrated build** — `lmmsobjs` + `ringbuffer` OBJECT
  libraries linked into `wavy-labs`; `LMMS_STATIC_DEFINE` added to suppress
  `__declspec(dllimport)` on Windows; `ENABLE_EXPORTS ON` so LMMS plugins
  resolve symbols from `wavy-labs.exe` at runtime
- **NSIS installer path fix** — `windows.nsi` updated to copy from `build/`
  (Ninja single-config, no Release subdir) and correctly stage theme + icons

### Changed
- `wavy-labs.exe` grows from 769 KB (standalone harness) to 7.2 MB because it
  now embeds the full LMMS engine + GUI

---

## [0.3.0] — 2026-03-03

### Added
- **First-launch onboarding wizard** (`wavy-ui/Dialogs/OnboardingWizard.cpp/.h`) —
  4-page QStackedWidget flow: Welcome → Model Download → License Key → Done;
  connects to `ModelManager` for live download progress and `LicenseManager` for
  key activation; shown exactly once via `QSettings` sentinel
- **License server hardening** (`wavy-license-server/`):
  - Alembic database migrations (`alembic.ini`, `migrations/env.py`,
    `migrations/versions/0001_initial_schema.py`) — schema changes are
    applied automatically on container start
  - Seat-limit enforcement — maximum 2 simultaneous activations per license key;
    `/activate` returns 409 when limit is reached
  - `/deactivate` endpoint decrements the active-seat counter
  - `/resend-key` endpoint re-sends the license key email to the purchaser
  - `email_sender.py` — Resend transactional email integration with graceful
    fallback to `loguru` log output in development
  - `start.sh` entrypoint that runs `alembic upgrade head` before launching
    `uvicorn`, ensuring migrations run on every container start
  - `Dockerfile` updated to use `start.sh` as CMD
  - `.dockerignore` excludes `.env`, `*.db`, `__pycache__`
  - `railway.toml` — Railway.app deployment config with `/health` healthcheck
  - Full test suite: `tests/conftest.py` (in-memory SQLite), 19 unit tests in
    `test_license_utils.py`, 30+ endpoint and webhook tests in `test_api.py`
- **Installer assets** (generated, committed to `data/icons/`):
  - `installer-banner.bmp` (164 × 314 px) — NSIS MUI2 welcome sidebar image
  - `installer-header.bmp` (150 × 57 px) — NSIS MUI2 header image
  - `dmg-background.png` (800 × 400 px) — macOS DMG background
  - `wavy-labs-256.png` (256 × 256 px) — Linux AppImage icon
  - `wavy-labs-1024.png` (1024 × 1024 px) — source image for macOS `.icns`
    (generate on macOS with `sips` + `iconutil`)
- **Documentation site** (MkDocs Material) at `docs/` covering all features,
  IPC protocol, RPC method reference, tiers, FAQ, and developer build guide;
  `mkdocs.yml` with Material theme, dark/light toggle, and search
- **License server CI** (`.github/workflows/license-server-tests.yml`) — pytest
  matrix across Ubuntu 22.04 / Windows / macOS 14 on Python 3.11 and 3.12;
  uploads coverage XML as artifact
- **DiffRhythm model support** (`wavy-ai/models/diffrhythm.py`):
  - `MODEL_ID = "ASLP-lab/DiffRhythm2"` (DiT weights, Apache 2.0)
  - `MODEL_ID_VAE = "ASLP-lab/DiffRhythm-vae"` (VAE, Stability AI Community License)
  - `vae_repo_id=` kwarg passed to `DiffRhythmPipeline.from_pretrained()`
- **`model_check.py` snapshot download support** — new `"snapshot": true` field
  in the model manifest triggers `huggingface_hub.snapshot_download()` instead
  of per-file `hf_hub_download()`; used by ACE-Step and DiffRhythm whose repos
  have non-flat directory layouts

### Changed
- `model_check.py` model manifest:
  - `ace_step` repo corrected to `ACE-Step/Ace-Step1.5` (was `ACE-Step/ACE-Step-v1.5`)
  - `ace_step` uses `snapshot: true` + `config.json` sentinel (was per-file)
  - `mixer` model changed to `required: false` — `wavy-labs/onnx-mixer-v1` does
    not yet exist on HuggingFace; rule-based fallback activates automatically
  - Two new optional entries: `diffrhythm` and `diffrhythm_vae`
- `wavy-ai/models/ace_step.py` `MODEL_ID` updated to `"ACE-Step/Ace-Step1.5"`
- `wavy-ui/CMakeLists.txt`:
  - `Qt6::SvgWidgets` added to link libraries (required for `QSvgWidget`)
  - `Qt6WebEngineWidgets` is now optional; `CodeEditor` source/header excluded
    from `wavy_ui` when the module is absent (MSYS2 mingw64 does not package it)
- Root `CMakeLists.txt` Qt6 find: `SvgWidgets` added to required components;
  `WebEngineWidgets` moved to an `OPTIONAL_COMPONENTS` call
- `build.yml` CI updated: Windows NSIS installer step, macOS `.icns` generation
  via `sips` + `iconutil`, Linux AppImage via `linuxdeployqt` + `appimagetool`
  (all `continue-on-error: true`)
- `release.yml` packaging prefers `.exe` / `.dmg` / `.AppImage` installer
  artifacts over raw binary zips
- `wavy-ai/pyproject.toml` `[docs]` extra added (mkdocs-material, minify,
  pymdown-extensions)
- `python-tests.yml` Windows runner: `PYTHONIOENCODING=utf-8` env var added to
  prevent `UnicodeEncodeError` on log lines that contain `✓`

### Fixed
- `wavy-installer/macos.sh` `Info.plist` — `CFBundleDocumentTypes` array was
  closed with `</dict>` instead of `</array>`; caused bundle validation failure
- `wavy-ui/AIPanel/AIPanel.h` — `m_isFreeUser` member was absent from the class
  declaration; added with default `true`
- `wavy-ui/ModelManager/ModelManagerPanel.cpp` — missing `#include <QStandardPaths>`
- `wavy-ui/ModelManager/ModelDownloader.h` — missing `#include <QFile>`
- `src/main.cpp` — `wavy-ui/` path prefix removed from includes (redundant given
  the `wavy-ui/` directory is already on the compiler include path)
- `wavy-license-server/` Stripe webhook: `line_items` expansion added to
  `checkout.session.completed` handler so `unit_amount` is accessible
- License server `/deactivate` endpoint now correctly decrements the active-seat
  counter (previously only removed the activation row)

---

## [0.2.0] — 2026-03-03

### Added
- **Best of 3 generation** — new "⚡×3 Best of 3" button fires 3 parallel
  `generateMusic()` calls with distinct seeds; a comparison dialog lets users
  preview and pick the best variation before inserting into the project
- **Color-coded stem tracks** — each stem output (vocals, drums, bass, guitar,
  piano, other) is inserted with a distinct track-header color for quick visual
  identification in the Song Editor
- `Song::addTrackFromAI()` extended with an optional `QColor` parameter;
  colors are applied via `track->setColor()`
- **Mixer channel AI Mix Assist** — right-click any FX Mixer channel to run
  AI analysis (`_runMixAssist`) or mastering (`_runMasterChannel`); suggestions
  are dispatched as LMMS automation patterns via `ActionDispatcher`
  (`FxMixerView.wavy.patch`)
- **7-day offline grace period** for Pro/Studio licenses — `LicenseManager`
  persists a `last_validated` timestamp; if re-validation fails because the
  server is unreachable, the tier stays active for 7 days before reverting to Free
- **OS keychain integration** — license keys can be stored in Windows Credential
  Manager / macOS Keychain / libsecret via the optional `WAVY_USE_KEYCHAIN` CMake
  flag (requires Qt6Keychain); falls back to XOR-obfuscated QSettings
- `LicenseManager::revalidateWithServer()` — async HTTPS POST to the license
  server every 7 days; emits `gracePeriodExpired()` signal if key is rejected
- Sentry crash reporting fully wired — `init_sentry()` is now called in
  `server.py:main()` immediately after logging configuration
- `build.sh` and `build.bat` — convenience one-shot build scripts for all
  platforms (wraps CMake + Ninja with sensible defaults)
- `wavy-installer/CMakeLists.txt` — platform-specific installer targets:
  NSIS on Windows, shell-based DMG on macOS, AppImage on Linux
- `CONTRIBUTING.md` — developer guide covering prerequisites, code style,
  commit format, and PR checklist
- `lmms-core/src/gui/SampleTrack.wavy.patch` — right-click "Wavy Labs AI →
  Split Stems…" context menu entry for `SampleTrackView`; Pro gate for 6-stem
- `wavy-ai/tests/test_rpc_handlers.py` — 30+ unit tests covering all 11 RPC
  methods using `MagicMock(spec=ModelRegistry)`; runs without GPU or model files

### Changed
- `AIPanel::setGenerating()` now also enables/disables `m_generateMultiBtn`
- `AIPanel::buildMusicTab()` generate area replaced with a two-button
  `QHBoxLayout` row (Generate 3 parts / Best of 3, 2 parts)
- `LicenseManager::tier()` now checks grace period before returning tier tier

### Fixed
- Missing `init_sentry()` call in `server.py:main()` — import was present but
  the function was never invoked

---

## [0.1.0] — 2026-02-10

### Added
- Initial monorepo structure (`lmms-core/`, `wavy-ui/`, `wavy-ai/`,
  `wavy-installer/`, `data/`)
- `lmms-core/` as a git submodule pointing to the LMMS Qt6 fork
- `wavy-ui` static library (`CMakeLists.txt`) with Qt6, ZeroMQ, nlohmann/json
- **AIClient** (`wavy-ui/IPC/AIClient.cpp/.h`) — ZeroMQ JSON-RPC client
  singleton with async callback model
- **ActionDispatcher** (`wavy-ui/IPC/ActionDispatcher.cpp/.h`) — maps JSON
  action objects to LMMS Engine API calls
- **LicenseManager** (`wavy-ui/LicenseGate/LicenseManager.cpp/.h`) — HMAC-
  SHA256 local key validation; Free / Pro / Studio tier detection
- **ModelManager** (`wavy-ui/ModelManager/ModelManager.cpp/.h`) — model
  download/update via Hugging Face Hub with SHA-256 checksum verification
- **AIPanel** (`wavy-ui/AIPanel/AIPanel.cpp/.h`) — MDI sub-window with three
  tabs: Generate Music, Vocal, Mix/Master
- **GenerationHistoryWidget** — scrollable history of past generations with
  audio path and duration
- **PromptBar** (`wavy-ui/PromptBar/PromptBar.cpp/.h`) — Ctrl+K command bar
  (Studio tier, wires to `prompt_command` RPC)
- **CodeEditor** (`wavy-ui/CodeToMusic/CodeEditor.cpp/.h`) — Monaco-based code
  editor via QWebEngineView for Wavy DSL / Python sonification (Studio tier)
- Python AI backend (`wavy-ai/server.py`) — ZeroMQ REP server, JSON-RPC 2.0
- `wavy-ai/rpc_handlers.py` — 11 RPC methods: `health`, `generate_music`,
  `split_stems`, `generate_vocal`, `mix_analyze`, `master_audio`,
  `prompt_command`, `code_to_music`, `list_models`, `load_model`, `unload_model`
- Model wrappers: `ace_step.py`, `diffrhythm.py`, `demucs.py`, `bark.py`,
  `mixer.py`, `prompt_cmd.py`, `code_music.py`
- `wavy-ai/config.py` — central constants (HOST, PORT, paths, model defaults)
- `wavy-ai/model_check.py` — first-run HuggingFace Hub model downloader with
  checksum verification
- `wavy-ai/crash_reporter.py` — Sentry SDK integration with DSN from env var
- `wavy-ai/pyproject.toml` — full Python project config with `[cuda]` and
  `[dev]` extras
- `wavy-ai/tests/` — pytest suite: RPC protocol, model registry, code-to-music,
  mixer, model_check
- LMMS fork patches: `MainWindow.wavy.patch`, `Song.wavy.patch`
  (adds `addTrackFromAI()` hook)
- Wavy Labs dark QSS theme (`data/themes/wavy-dark/style.qss`) with
  `#0d0d14` background and `#7c5cbf` / `#4fc3f7` accent colors
- SVG icon set: `ai-panel.svg`, `stems.svg`, `code.svg`, `wavy-labs.svg`
- Qt resources: `data/resources.qrc`
- `.gitmodules` — submodules for lmms-core, vendor/cppzmq, vendor/json
- `vendor/bootstrap.sh` + `vendor/bootstrap.bat` — one-shot submodule init
- `.github/workflows/build.yml` — Win/Mac/Linux CI via jurplel/install-qt-action
- `.github/workflows/python-tests.yml` — pytest on 3 OS × 3 Python versions
- `.github/workflows/release.yml` — tag-triggered draft release with installers
- `wavy-installer/version.rc.in` — Windows version resource template
- `LICENSE` (GPL-2.0), `README.md`, `.gitignore`

---

[Unreleased]: https://github.com/wavy-labs/wavy-labs/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/wavy-labs/wavy-labs/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wavy-labs/wavy-labs/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wavy-labs/wavy-labs/releases/tag/v0.1.0
