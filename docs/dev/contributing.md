# Contributing

Contributions are welcome! Please read this guide before opening a PR.

## Code of Conduct

Be respectful and constructive. We follow the
[Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## Before You Start

- Open a GitHub Issue for any non-trivial change.
- Discuss the approach before investing significant time in implementation.
- Check existing Issues and PRs to avoid duplicate work.

## Development Setup

See [Building from Source](building.md) for the full environment setup.

## C++ Style Guide

- Standard: **C++20**
- Follow Qt coding style — `camelCase` for variables/methods, `PascalCase` for types
- Class members: `m_camelCase` prefix
- No raw `new` without a matching parent/owner (prefer RAII)
- Use `Q_ASSERT` for internal invariants, `QMessageBox` for user-visible errors
- `#ifdef WAVY_LMMS_CORE` for all LMMS-specific code in patches

## Python Style Guide

- Formatter: **black** (`black wavy-ai/`)
- Linter: **ruff** (`ruff check wavy-ai/`)
- Type hints: required for all public functions
- Docstrings: Google style

## Commit Message Format

```
<type>: <short summary> (≤72 chars)

<body — optional, explains WHY not WHAT>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `chore`

Examples:

```
feat: add Best of 3 multi-attempt generation dialog
fix: grace period timer resets correctly after re-validation
docs: add IPC protocol reference page
```

## Pull Request Checklist

- [ ] Tests added or updated for changed code
- [ ] `pytest tests/ -v` passes (Python)
- [ ] No new compiler warnings (C++)
- [ ] `black` and `ruff` clean (Python)
- [ ] CHANGELOG.md entry added under `[Unreleased]`
- [ ] PR title follows commit message format

## Testing

```bash
# Python — unit tests (no GPU required)
cd wavy-ai && pytest tests/ -v

# Python — with coverage
pytest tests/ --cov=wavy_ai --cov-report=term-missing
```

C++ tests will be added in v0.3 using Qt Test.

## License

By contributing, you agree that your contributions are licensed under **GPL-2.0**
(for the C++ DAW code) or **MIT** (for the Python AI backend in `wavy-ai/`),
matching the license of the file you modify.
