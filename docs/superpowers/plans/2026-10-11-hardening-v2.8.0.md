# v2.8.0 운영 안정화(하드닝) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-10-11 전체 코드 리뷰에서 나온 운영 리스크·버그·정리 항목을 v2.8.0으로 묶어 해결한다.

**Architecture:** 기존 `app/` 패키지 구조를 유지하고 각 모듈에 최소 변경을 가한다. win32 비의존 로직(설정 저장, 로그 회전, 큐 비우기, IP 폴백, 템플릿 id)은 WSL에서 unittest로 검증하고, win32·PIL 의존 변경(키오스크 종료, EXIF, 자동 실행 경로)은 Windows 스모크 테스트 항목으로 넘긴다. 외부 repo는 낡은 배포 산출물을 제거하고 문서를 현재 버전에 맞춘다.

**Tech Stack:** Python 3.12, FastAPI/uvicorn, PIL, customtkinter, stdlib unittest, GitHub Actions(windows-latest)

## Global Constraints

- 소스 커밋은 `src/`(원격 `coredot-printer-src`), 문서 커밋은 외부 repo — 둘 다 main
- 테스트는 `cd src && python3 -m unittest discover -s tests -v` (pytest 없음, WSL에는 PIL 없음)
- 스코프 제외 합의 유지: 인쇄 종횡비 변경, 설정 자동 저장, 트레이 최소화, API 토큰 인증
- API 응답 형식이 바뀌면 `dev/printer_mock.py`를 같은 커밋 흐름에서 동기화
- 버전: `src/app/__init__.py` VERSION=2.8.0, `src/app/changelog.py`·`CHANGELOG.md` 동시 갱신

---

### Task 1: config.json 원자적 저장

**Files:** Modify `src/app/config.py:48-53`, Test `src/tests/test_config.py`

- [x] 테스트 추가: 저장 후 같은 폴더에 `.tmp` 잔여물이 없고, 저장 실패(디렉토리 없음) 시 예외 대신 경고만 남는다.
- [x] `_save_locked`: `tempfile.mkstemp(dir=dirname, suffix=".tmp")` → `json.dump` → `os.replace(tmp, self.path)`; 실패 시 tmp 삭제.
- [x] 테스트 통과 확인, 커밋 `fix: config.json 원자적 저장 (전원 차단 시 설정 유실 방지)`

### Task 2: error.log 회전 + 라인 버퍼링

**Files:** Modify `src/printer_server.py:81-86`, Test `src/tests/test_entry.py`

- [x] `_rotate_error_log(base_dir)`: `error.log`가 있고 크기>0이면 `error.log.1`로 `os.replace`. 테스트: 회전 후 `.1`에 이전 내용, 새 파일은 비어 있음.
- [x] stderr open에 `buffering=1` 추가.
- [x] 커밋 `fix: error.log 이전 로그 보존(error.log.1) + 라인 버퍼링`

### Task 3: /health 식별 정보 + 중복 실행 감지 강화

**Files:** Modify `src/app/api.py:116-119`, `src/printer_server.py:60-71`, `dev/printer_mock.py`

- [x] `/health` → `{"status":"ok","app":"coredot-printer","version":VERSION}`
- [x] `_already_running`: `'"coredot-printer"' in body` 로 판정. 테스트: `urlopen` mock으로 ok/타서버 분기.
- [x] 모의 서버 동일 응답. 커밋.

### Task 4: 원격 제어 제한 (`/shutdown`, `/close-kiosk`)

**Files:** Modify `src/app/api.py`, `src/app/gui.py`(체크박스), `src/app/config.py` 없음(키만), `dev/printer_mock.py`(주석)

- [x] `api.py`: `_require_local_or_remote_control(request)` — `config.get("allow_remote_control", False)`가 False이고 `request.client.host`가 `127.0.0.1`/`::1`이 아니면 403 `"원격 제어가 허용되지 않았습니다 (같은 PC에서만 가능)."`.
- [x] 두 엔드포인트에 `request: Request` 주입 후 호출.
- [x] GUI [기본] 탭 자동실행 행 아래에 체크박스 "원격 종료·키오스크 제어 허용 (같은 네트워크)" → `allow_remote_control` 저장, 로그 출력.
- [x] 커밋 `feat: 원격 제어(/shutdown, /close-kiosk) 기본 차단 — allow_remote_control 설정`

### Task 5: /templates 응답에 id + GUI 키를 id로

**Files:** Modify `src/app/api.py:167-178`, `src/app/gui.py` `_refresh_templates/_apply_templates/_on_template_selected/_save_layout`, `dev/printer_mock.py`, `src/tests/test_template.py`

- [x] `list_templates` 응답 각 항목에 `"id": t["id"]` 추가. 모의 서버 `TEMPLATES[0]["id"]="감사장"`.
- [x] GUI `_templates = {t["id"]: t}`; 콤보 표시값 = id; `_save_layout`은 `self._templates[saved["id"]]`.
- [x] 커밋 `fix: /templates 응답·GUI 템플릿 키를 파일명(id) 기준으로 통일`

### Task 6: 프린터 일시 미연결 시 선택 유지

**Files:** Modify `src/app/gui.py` `_apply_printer_data`, `_apply_saved_printer`, `_update_status_label`, `_set_combo_display`

- [x] `_apply_printer_data`: `current`가 비어 있을 때만 기본 프린터로 대체. 비어 있지 않고 목록에 없으면 유지.
- [x] `_update_status_label`/`_set_combo_display`: 목록에 없는 선택은 "미연결" (red).
- [x] `_apply_saved_printer`: 저장 프린터가 목록에 없어도 선택(미연결 표시) — 재연결 시 그대로 사용.
- [x] 커밋 `fix: 프린터가 잠시 사라져도 선택 유지 (미연결 표시)`

### Task 7: 키오스크 Chrome 핸들 유실 수정

**Files:** Modify `src/app/kiosk.py`, Test `src/tests/test_kiosk.py`(subprocess mock)

- [x] `open_kiosk`: 기존 핸들이 살아 있으면(`poll() is None`) `terminate()`+`wait(3)` 후 새로 실행 (hand-off 방지).
- [x] `_kill_by_profile_dir()`: PowerShell `Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%CoreDotKiosk%'"` 로 잔여 프로세스 강제 종료 (CREATE_NO_WINDOW). 반환: 종료 시도 여부.
- [x] `close_kiosk`: 핸들 terminate (살아 있을 때) + 항상 sweep. 둘 다 아무것도 없으면 `no_process`.
- [x] 테스트: Popen/run mock으로 (a) 두 번 open 시 첫 핸들 terminate 호출, (b) 핸들 죽었어도 sweep 호출.
- [x] 커밋 `fix: 키오스크 Chrome 재실행 시 핸들 유실·종료 실패 수정`

### Task 8: 업로드 사진 EXIF 회전 + URL 다운로드 크기 제한 + 미리보기 dpi 상한

**Files:** Modify `src/app/compose.py`, `src/app/api.py:147-148`

- [x] `_load_image_param`: `ImageOps.exif_transpose(img)` 적용; URL/data URI 디코드 결과가 `MAX_IMAGE_BYTES`(20MB) 초과면 `TemplateParamError`.
- [x] `PREVIEW_DPI_MAX = 300`.
- [x] 커밋 `fix: 업로드 사진 EXIF 회전 반영, 원격 이미지 20MB 제한, 미리보기 dpi 상한 300`

### Task 9: 업로드 크기·큐 길이 제한

**Files:** Modify `src/app/api.py` `print_image`/`print_template`, `src/app/jobs.py`, Test `src/tests/test_jobs.py`

- [x] `jobs.PrintJobQueue(max_queued=20)`; `submit`가 대기 중(`queued`) 작업이 상한이면 `QueueFull` 예외. 테스트.
- [x] API: `QueueFull` → 503 `"인쇄 대기열이 가득 찼습니다. 잠시 후 다시 시도하세요."`; 업로드는 청크 복사하며 `MAX_UPLOAD_BYTES`(50MB) 초과 시 413.
- [x] 커밋 `fix: 업로드 50MB·대기열 20건 제한`

### Task 10: 종료 시 대기 작업 정리 + 인쇄 문서명

**Files:** Modify `src/app/jobs.py`, `src/app/printing.py:115`, `src/app/gui.py` `on_closing`, Test `src/tests/test_jobs.py`

- [x] `jobs.drain()`: 큐의 남은 항목을 꺼내 임시 파일 삭제, 상태 `error`("앱 종료로 취소됨"). 테스트.
- [x] `print_func(path, printer, doc_name)` 3-인자로 변경; `print_without_margins(path, printer, doc_name=None)` → `StartDoc(doc_name or basename)`.
- [x] `on_closing`에서 `jobs.drain()`.
- [x] 커밋 `fix: 종료 시 대기 인쇄 임시 파일 정리, 인쇄 대기열 문서명을 원본 파일명으로`

### Task 11: 자동 실행 경로 자동 갱신

**Files:** Modify `src/app/autostart.py`, `src/app/gui.py` `_apply_saved_printer`

- [x] `registered_command()` → 레지스트리 값 또는 None; `ensure_current_path()` → 등록돼 있고 현재 exe 경로와 다르면 재등록, (갱신 여부, 오류) 반환.
- [x] GUI: auto_start 켜진 상태로 기동 시 `ensure_current_path()` 호출, 갱신되면 로그.
- [x] 커밋 `fix: exe 이동·이름 변경 시 자동 실행 레지스트리 경로 자동 갱신`

### Task 12: server.log 회전 파일 로그 + 내부 IP 폴백

**Files:** Modify `src/app/server.py`, `src/app/netutil.py`, Test `src/tests/test_netutil.py`

- [x] `server.py`: 모듈 레벨 `_file_handler()` — `RotatingFileHandler(<exe 옆>/server.log, maxBytes=1MB, backupCount=3, encoding=utf-8)` 지연 생성; uvicorn/app 로거 핸들러에 큐 핸들러와 함께 추가.
- [x] `netutil.get_local_ip`: UDP 실패 시 `socket.gethostbyname_ex(socket.gethostname())`의 비-127 주소 첫 번째, 없으면 "localhost". 테스트.
- [x] 커밋.

### Task 13: 소소한 수정 묶음

**Files:** `src/app/template.py:126`, `src/app/compose.py` 축소 루프, `src/app/gui.py`(MIN_FONT_PT, QR 샘플값, 창 세로 리사이즈)

- [x] dpi: `float`이면서 정수값이면 `int()`로 허용. 테스트.
- [x] 축소 루프: `size_pt = max(MIN_FONT_PT, size_pt - 1)` 후 `size_pt == MIN_FONT_PT`면 마지막 한 번 렌더하고 종료.
- [x] GUI: `size_pt < tpl.MIN_FONT_PT`; QR required 샘플값 `"https://core.today"`; `resizable(False, True)` + `minsize(680, 700)`.
- [x] 커밋.

### Task 14: 버전 2.8.0·릴리스 노트·요구사항 고정·CI·레거시 삭제

**Files:** `src/app/__init__.py`, `src/app/changelog.py`, `src/requirements.txt`, `src/.github/workflows/ci.yml`, 삭제 `src/main2.py`, `src/printer_launcher.py`

- [x] requirements 고정 (build_venv 실측): fastapi==0.135.1, uvicorn[standard]==0.41.0, python-multipart==0.0.22, pillow==12.1.1, pywin32==311, customtkinter==5.2.2, qrcode==8.x(실측 확인), nuitka==4.0.2, ordered-set==4.1.0
- [x] CI: push/PR → windows-latest 에서 unittest; `workflow_dispatch`/태그 → build_release.py 후 exe 아티팩트 업로드.
- [x] 커밋 `chore: v2.8.0 — 의존성 고정, CI, 레거시 파일 삭제`

### Task 15: 외부 repo 정리·문서

**Files:** 삭제 `프린터서버.exe`, `_internal/`, `install.cmd`, `%NVM_HOME%PATH.txt`, `README.txt`; 수정 `help.md`, `docs/smoke-test.md`, `CHANGELOG.md`, `CLAUDE.md`, `README.md`

- [x] `git rm -r` 낡은 산출물.
- [x] help.md: v2.8 API 전체(templates/print-template/preview/print-jobs/health/close-kiosk/shutdown), 설정 항목, 문제 해결(미연결·원격 제어 403·server.log 위치).
- [x] smoke-test.md: 릴리스 노트 항목 버전 갱신 + v2.8.0 섹션(설정 원자 저장·error.log.1·미연결 표시·원격 제어 403·키오스크 재실행·EXIF·server.log·자동실행 경로 갱신).
- [x] CLAUDE.md: config 키(`allow_remote_control`), `/health` 형식, `/templates` id, 소스 원격 repo 안내, 현재 버전 2.8.0.
- [x] 커밋.
