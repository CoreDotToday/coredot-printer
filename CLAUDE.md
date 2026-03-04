# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CoreDotToday AI Kiosk Printer Server — a Windows desktop application that exposes local printers as an HTTP API. Built with Python, it bundles a Tkinter GUI launcher and a FastAPI server into a single standalone `.exe` via Nuitka (Python → C compiler).

- **Platform:** Windows 10/11 only
- **Language:** Korean (UI, docs, filenames)
- **Distribution:** Single `프린터서버.exe` — no Python needed on target machines

## Build & Run

Source code lives in `src/` (gitignored — not tracked in the repo).

```bash
# Install dependencies
pip install -r src/requirements.txt

# Run from source
python src/printer_server.py

# Build standalone exe (from src/ directory)
python src/build_release.py
# Output: src/dist/프린터서버.exe → copied to src/release/
```

Dependencies: `fastapi`, `uvicorn[standard]`, `python-multipart`, `pillow`, `pywin32`, `psutil`, `tkinter` (stdlib)

No test suite or linter is configured.

## Architecture

**`printer_server.py`** is the single integrated application (GUI + server):

1. **FastAPI server** (`api`) — runs on `0.0.0.0:8000` in a background thread via `UvicornServer`
2. **Tkinter GUI** (`PrinterAPILauncher`) — controls server start/stop, printer selection, log display
3. **Windows printing** — `win32print`/`win32ui` for printer enumeration; `PIL.ImageWin` for zero-margin image printing via device context manipulation

Other source files:
- `main2.py` — standalone FastAPI server without GUI (headless alternative)
- `printer_launcher.py` — older launcher that spawns `main2.py` as a subprocess
- `build_release.py` — Nuitka build script (replaces PyInstaller for antivirus-friendly builds)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/printers` | List installed printers |
| `POST` | `/print-image` | Print image (`multipart/form-data`: `file` required, `printer` optional) |
| `GET` | `/health` | Server health check |
| `GET` | `/docs` | Swagger UI |

## Key Implementation Details

- **Zero-margin printing**: Negative offsets equal to physical printer margins are applied to the device context draw coordinates (`print_without_margins`)
- **Duplicate instance prevention**: Uses `psutil` to scan for existing `프린터서버` processes at startup
- **Build**: Nuitka `--mode=onefile` compiles Python to native C binary. Requires Visual Studio Build Tools on build machine
- **CORS**: Wide-open (`allow_origins=["*"]`) for kiosk client access
