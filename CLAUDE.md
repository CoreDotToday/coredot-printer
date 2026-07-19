# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CoreDotToday AI Kiosk Printer Server — a Windows desktop application that exposes local printers as an HTTP API. Built with Python, it bundles a customtkinter GUI launcher and a FastAPI server into a single standalone `.exe` via Nuitka (Python → C compiler).

- **Platform:** Windows 10/11 only (`win32print`, `winreg`, etc. — cannot run on Linux/WSL)
- **Language:** Korean (UI, docs, filenames, code comments)
- **Distribution:** Single `프린터서버.exe` — no Python needed on target machines

The outer repo tracks only distribution files and docs; **source code lives in `src/`, which is gitignored by the outer repo but has its own nested git repository** — commit source changes inside `src/`, docs in the outer repo.

## Build, Run & Test

```bash
# Run from source (Windows only)
pip install -r src/requirements.txt
python src/printer_server.py

# Unit tests (pure-logic modules; runnable on WSL/Linux, stdlib unittest — no pytest)
cd src && python3 -m unittest discover -s tests -v

# Build standalone exe (Windows, from src/, in a dedicated venv — see the `command` file)
python -m venv build_venv
.\build_venv\Scripts\activate
pip install -r requirements.txt
python build_release.py
# Output: src/dist/프린터서버.exe → copied to src/release/
```

Before a release build, run the manual checklist in `docs/smoke-test.md` on a real Windows machine.

**Release flow**: bump `VERSION` in `src/app/__init__.py` + update `src/app/changelog.py` and `CHANGELOG.md` → build on Windows (`build_release.py` also produces `src/release/CoreDotPrinter-<tag>.exe`) → smoke test → publish from WSL with `scripts/publish_release.sh` (tag = major.minor, notes auto-extracted from `CHANGELOG.md`; `--dry-run` to preview).

Dependencies: `fastapi`, `uvicorn[standard]`, `python-multipart`, `pillow`, `pywin32`, `customtkinter`; build-time: `nuitka`, `ordered-set`.

## Architecture (v2.4.0)

`src/printer_server.py` is a ~100-line entry point (console hiding, stderr→error.log, duplicate-instance check via `/health` probe, GUI launch). The application lives in `src/app/`:

- `__init__.py` — VERSION and global constants (no external imports; importable anywhere)
- `config.py` — thread-safe `Config` singleton over `config.json` (next to the exe); validated `port` property
- `jobs.py` — `PrintJobQueue`: single worker thread prints sequentially, tracks job status (`queued/printing/done/error`), guarantees temp-file cleanup; `print_func` injected so it's testable without win32
- `printing.py` / `autostart.py` — the only win32-dependent modules (printer enum/status/zero-margin printing; HKCU Run registry)
- `kiosk.py` — Chrome kiosk launch/close (dedicated profile dir under `%LOCALAPPDATA%\CoreDotKiosk`)
- `api.py` — FastAPI endpoints; pre-validates printer + image and returns 4xx before queueing; owns the GUI-selected-printer state
- `server.py` — `UvicornServer` background-thread wrapper (`started` property for reliable start detection, join-based `stop`, `/health` access-log filter)
- `gui.py` — customtkinter launcher; printer status queried in background threads (30s auto-refresh), 1,000-line log ring buffer, server-poll generation tokens

Legacy files superseded by the package: `main2.py`, `printer_launcher.py`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/printers` | List installed printers + default |
| `POST` | `/print-image` | Print image (`multipart/form-data`: `file` required, `printer` optional); returns `job_id`; 400 on unknown printer / invalid image |
| `GET` | `/print-jobs/{job_id}` | Job status: `queued` / `printing` / `done` / `error` |
| `GET` | `/health` | Health check (also used for duplicate-instance detection) |
| `POST` | `/close-kiosk` | Terminate the kiosk Chrome process |
| `POST` | `/shutdown` | Shut down Windows (5s delay) |
| `GET` | `/docs` | Swagger UI |

Printer selection priority for `/print-image`: request `printer` param > GUI-selected printer > Windows default printer.

## Key Implementation Details

- **Versioning**: `VERSION` in `app/__init__.py`, release notes in `app/changelog.py` (`CHANGELOG` list) — update both when releasing; mirror in the outer repo's `CHANGELOG.md`. Current: v2.4.0
- **Config keys** (`config.json`): `port`, `printer`, `auto_start`, `saved_urls`, `kiosk_url`, `kiosk_auto_open`, `kiosk_zoom`, `allow_external`
- **접속 범위**: `allow_external` (default `true`) binds `0.0.0.0` (LAN reachable) vs `127.0.0.1` (same PC only); applied on server (re)start
- **Zero-margin printing**: negative offsets equal to physical printer margins in device-context draw coordinates (`app/printing.py`); image is stretched to the printable area by design — do not "fix" the aspect ratio
- **Error diagnostics**: stdout discarded, stderr → `error.log` next to the exe; `logging` warnings from `app.*` also surface in the GUI log
- **Build**: Nuitka `--mode=onefile` with `--enable-plugin=tk-inter` and explicit `--include-package` flags (incl. `app`) — adding a new dependency usually requires adding it to `build_release.py`. Do NOT use `--zig`: zig's linker emits a `.pdb` that makes Nuitka onefile builds fail with a FATAL (see `docs/nuitka-customtkinter-guide.md`)
- **CORS**: wide-open (`allow_origins=["*"]`) for kiosk client access
- **Mock server contract**: `dev/printer_mock.py` mirrors the real API for mac/linux kiosk developers — update it whenever endpoints or response shapes change
