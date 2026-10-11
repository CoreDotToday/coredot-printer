# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CoreDotToday AI Kiosk Printer Server — a Windows desktop application that exposes local printers as an HTTP API. Built with Python, it bundles a customtkinter GUI launcher and a FastAPI server into a single standalone `.exe` via Nuitka (Python → C compiler).

- **Platform:** Windows 10/11 only (`win32print`, `winreg`, etc. — cannot run on Linux/WSL)
- **Language:** Korean (UI, docs, filenames, code comments)
- **Distribution:** Single `프린터서버.exe` — no Python needed on target machines

The outer repo tracks only docs and the dev mock server; **source code lives in `src/`, which is gitignored by the outer repo but is its own git repository** with remote `https://github.com/CoreDotToday/coredot-printer-src` (private, branch `main`) — commit and push source changes inside `src/`, docs in the outer repo. Binaries are distributed via GitHub Releases only (no exe in either repo).

## Build, Run & Test

```bash
# Run from source (Windows only)
pip install -r src/requirements.txt
python src/printer_server.py

# Unit tests (pure-logic modules; runnable on WSL/Linux, stdlib unittest — no pytest)
cd src && python3 -m unittest discover -s tests -v

# Build standalone exe (Windows, from src/, in a dedicated venv)
python -m venv build_venv
.\build_venv\Scripts\activate
pip install -r requirements.txt
python build_release.py
# Output: src/dist/프린터서버.exe → copied to src/release/
```

Before a release build, run the manual checklist in `docs/smoke-test.md` on a real Windows machine. The src repo also has GitHub Actions CI (`.github/workflows/ci.yml`): unit tests + full import on `windows-latest` for every push; Nuitka build with exe artifact on `v*` tags or manual dispatch.

**Release flow**: bump `VERSION` in `src/app/__init__.py` + update `src/app/changelog.py` and `CHANGELOG.md` → build on Windows (`build_release.py` also produces `src/release/CoreDotPrinter-<tag>.exe`) → smoke test → publish from WSL with `scripts/publish_release.sh` (tag = major.minor, notes auto-extracted from `CHANGELOG.md`; `--dry-run` to preview).

Dependencies (pinned in `src/requirements.txt`): `fastapi`, `uvicorn[standard]`, `python-multipart`, `pillow`, `pywin32`, `customtkinter`, `qrcode`; build-time: `nuitka`, `ordered-set`.

## Architecture (v2.4.0)

`src/printer_server.py` is a ~100-line entry point (console hiding, stderr→error.log, duplicate-instance check via `/health` probe, GUI launch). The application lives in `src/app/`:

- `__init__.py` — VERSION and global constants (no external imports; importable anywhere)
- `config.py` — thread-safe `Config` singleton over `config.json` (next to the exe); atomic save (tmp + `os.replace`); validated `port` property
- `jobs.py` — `PrintJobQueue`: single worker thread prints sequentially, tracks job status (`queued/printing/done/error`), guarantees temp-file cleanup, `max_queued` limit (`QueueFull` → 503), `drain()` on app exit; `print_func(path, printer, doc_name)` injected so it's testable without win32
- `printing.py` / `autostart.py` — the only win32-dependent modules (printer enum/status/zero-margin printing; HKCU Run registry)
- `kiosk.py` — Chrome kiosk launch/close (dedicated profile dir under `%LOCALAPPDATA%\CoreDotKiosk`); closes the previous instance before relaunch and sweeps by profile dir via PowerShell, since Chrome hands off to an existing instance and the Popen handle dies
- `template.py` — template JSON load/validate/schema (PIL-free, WSL-testable); user assets in `data/`, bundled in `assets/`
- `compose.py` — PIL+qrcode renderer (text wrap/shrink, cover/contain images, QR) — same code path for preview and print
- `api.py` — FastAPI endpoints; pre-validates printer + image and returns 4xx before queueing; upload limit 50MB (413); `/shutdown`·`/close-kiosk` are loopback-only unless `allow_remote_control` (403); owns the GUI-selected-printer state
- `server.py` — `UvicornServer` background-thread wrapper (`started` property for reliable start detection, join-based `stop`, `/health` access-log filter, rotating `server.log` 1MB×3 next to the exe)
- `gui.py` — customtkinter launcher; printer status queried in background threads (30s auto-refresh; a selected printer that disappears stays selected and shows "미연결"), 1,000-line log ring buffer, server-poll generation tokens; tabbed UI ([기본]=server+kiosk on one screen / [템플릿]) with server-independent template preview/test-print; template layout editor keyed by template `id` with live in-window preview (debounced compose.render at dpi 72)

Pure-logic tests exist for config, jobs, template, netutil, kiosk (subprocess mocked), changelog and the entry point.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/printers` | List installed printers + default |
| `POST` | `/print-image` | Print image (`multipart/form-data`: `file` required, `printer` optional); returns `job_id`; 400 on unknown printer / invalid image |
| `GET` | `/print-jobs/{job_id}` | Job status: `queued` / `printing` / `done` / `error` |
| `GET` | `/templates` | List template layouts (`id` = file stem used as the `template` value, `name` = display) + parameter schema |
| `POST` | `/print-template` | Compose and print a template (e.g. certificate); 503 when the queue holds 20 jobs |
| `GET` | `/preview-template` | Template composition preview (PNG); `dpi` 72–300 |
| `GET` | `/health` | `{"status":"ok","app":"coredot-printer","version":...}` (duplicate-instance detection keys on `app`) |
| `POST` | `/close-kiosk` | Terminate the kiosk Chrome process (403 from non-loopback unless `allow_remote_control`) |
| `POST` | `/shutdown` | Shut down Windows (5s delay) (403 from non-loopback unless `allow_remote_control`) |
| `GET` | `/docs` | Swagger UI |

Printer selection priority for `/print-image`: request `printer` param > GUI-selected printer > Windows default printer.

## Key Implementation Details

- **Versioning**: `VERSION` in `app/__init__.py`, release notes in `app/changelog.py` (`CHANGELOG` list) — update both when releasing; mirror in the outer repo's `CHANGELOG.md`. Current: v2.8.0
- **Config keys** (`config.json`): `port`, `printer`, `auto_start`, `saved_urls`, `kiosk_url`, `kiosk_auto_open`, `kiosk_zoom`, `allow_external`, `allow_remote_control`
- **원격 제어**: `allow_remote_control` (default `false`) — `/shutdown`·`/close-kiosk` accept only loopback requests unless enabled; checked per request (no restart needed). Token auth was deliberately excluded from scope.
- **Logs next to the exe**: `error.log` (stderr, WARNING+; previous run kept as `error.log.1`), `server.log` (INFO, uvicorn access + app, 1MB×3 rotation)
- **접속 범위**: `allow_external` (default `true`) binds `0.0.0.0` (LAN reachable) vs `127.0.0.1` (same PC only); applied on server (re)start
- **Zero-margin printing**: negative offsets equal to physical printer margins in device-context draw coordinates (`app/printing.py`); image is stretched to the printable area by design — do not "fix" the aspect ratio
- **Error diagnostics**: stdout discarded, stderr → `error.log` next to the exe (line-buffered); `logging` from `app.*` surfaces in the GUI log and `server.log`
- **Image params**: uploads are EXIF-transposed (`ImageOps.exif_transpose`); remote URLs are fetched with a 20MB cap and **no private-IP block** (LAN image servers are a legitimate use)
- **Build**: Nuitka `--mode=onefile` with `--enable-plugin=tk-inter` and explicit `--include-package` flags (incl. `app`) — adding a new dependency usually requires adding it to `build_release.py`. Do NOT use `--zig`: zig's linker emits a `.pdb` that makes Nuitka onefile builds fail with a FATAL (see `docs/nuitka-customtkinter-guide.md`)
- **CORS**: wide-open (`allow_origins=["*"]`) for kiosk client access
- **Template schema**: see `docs/superpowers/specs/2026-07-19-template-printing-design.md`; coordinates in mm, fonts/backgrounds resolved from `data/` first then bundled `assets/`
- **Mock server contract**: `dev/printer_mock.py` mirrors the real API for mac/linux kiosk developers — update it whenever endpoints or response shapes change
