# 프린터 서버 v2.4.0 리팩토링 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `src/printer_server.py`(1,466줄)를 `app/` 패키지로 분리하고 GUI 블로킹·인쇄 피드백·서버 수명주기·로그 증가 문제를 수정하여 v2.4.0을 만든다.

**Architecture:** 진입점 `printer_server.py`는 유지하고 본체를 `app/` 패키지 9개 모듈로 분리한다. win32 의존은 `printing.py`/`autostart.py`에 격리하고, 순수 로직(`config`, `jobs`, `changelog`)은 WSL에서 stdlib `unittest`로 테스트한다. 인쇄는 전용 워커 스레드 큐로, 프린터 상태 조회는 GUI 백그라운드 스레드로 옮긴다.

**Tech Stack:** Python 3.13, FastAPI/uvicorn, customtkinter, pywin32, PIL, Nuitka. 테스트는 stdlib `unittest`(WSL에 pip이 없어 pytest 설치 불가 — 스펙의 "pytest" 항목을 unittest로 대체, 목표 동일).

**전제 조건:**
- 스펙: `docs/superpowers/specs/2026-07-19-refactoring-v2.4.0-design.md`
- `src/`는 외부 repo에서 gitignore됨 → **Task 1에서 `src/` 내부에 중첩 git 저장소를 초기화**하고, 이후 모든 소스 커밋은 `src/` 저장소에서 수행한다. 문서 커밋만 외부 repo에서 한다.
- 이 환경(WSL)에서는 win32/fastapi 코드를 실행할 수 없다. 실행 검증은 `python3 -m unittest`(순수 로직)와 `python3 -m py_compile`(문법)까지만 하고, 통합 동작은 Windows 스모크 테스트(Task 12의 체크리스트)로 확인한다.
- 모든 명령은 별도 표기가 없으면 `src/` 디렉토리에서 실행한다.

---

### Task 1: src/ 내부 git 저장소 초기화

**Files:**
- Create: `src/.gitignore`

- [ ] **Step 1: git 저장소 초기화 및 .gitignore 작성**

```bash
cd /mnt/c/Users/kyunghoon/projects/coredot-printer/src
git init
```

`src/.gitignore` 내용:

```gitignore
__pycache__/
*.py[cod]
build_venv/
dist/
release/
error.log
*.pdb
```

- [ ] **Step 2: 베이스라인 커밋**

```bash
git add .gitignore printer_server.py main2.py printer_launcher.py build_release.py requirements.txt printer.ico
git commit -m "chore: v2.3.0 베이스라인 (리팩토링 시작점)"
```

Expected: 커밋 성공, `git log --oneline` 1건.

---

### Task 2: app 패키지 뼈대 + 테스트 디렉토리

**Files:**
- Create: `src/app/__init__.py`
- Create: `src/tests/__init__.py`

- [ ] **Step 1: `src/app/__init__.py` 작성**

win32/fastapi를 import하지 않는 순수 상수 모듈 — 어떤 플랫폼에서도 import 가능해야 한다.

```python
# -*- coding: utf-8 -*-
"""앱 전역 상수. 외부 의존성 없이 어디서든 import 가능해야 한다."""

VERSION = "2.4.0"
APP_NAME = "코어닷투데이 프린터 API 서버"
APP_COPYRIGHT = "© 2026 CoreDot Today"
HELP_URL = "https://github.com/CoreDotToday/coredot-printer/blob/main/help.md"

DEFAULT_PORT = 8000
PORT_MIN = 1024
PORT_MAX = 65535
```

- [ ] **Step 2: 빈 `src/tests/__init__.py` 생성 후 import 확인**

```bash
touch tests/__init__.py
python3 -c "import app; print(app.VERSION)"
```

Expected: `2.4.0`

- [ ] **Step 3: Commit**

```bash
git add app/__init__.py tests/__init__.py
git commit -m "feat: app 패키지 뼈대 (전역 상수)"
```

---

### Task 3: app/changelog.py — 데이터 이동 + 태그 파서 (TDD)

**Files:**
- Create: `src/app/changelog.py`
- Test: `src/tests/test_changelog.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/tests/test_changelog.py`:

```python
# -*- coding: utf-8 -*-
import unittest

from app.changelog import CHANGELOG, parse_change


class ParseChangeTest(unittest.TestCase):
    def test_tagged_change(self):
        self.assertEqual(parse_change("[추가] 새 기능"), ("추가", "새 기능"))

    def test_untagged_change(self):
        self.assertEqual(parse_change("그냥 설명"), (None, "그냥 설명"))

    def test_bracket_not_at_start(self):
        self.assertEqual(parse_change("설명 [참고] 포함"), (None, "설명 [참고] 포함"))

    def test_changelog_shape(self):
        # (버전, 날짜, 변경 목록) 튜플 리스트여야 한다
        for version, date, changes in CHANGELOG:
            self.assertIsInstance(version, str)
            self.assertIsInstance(date, str)
            self.assertIsInstance(changes, list)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

```bash
python3 -m unittest tests.test_changelog -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.changelog'`

- [ ] **Step 3: `src/app/changelog.py` 구현**

`CHANGELOG` 리스트는 `printer_server.py` 73–105행의 내용을 그대로 옮긴다(v2.3.0~v1.0.0 전체). 파일 구조:

```python
# -*- coding: utf-8 -*-
"""릴리스 노트 데이터 및 항목 파서."""

CHANGELOG = [
    # printer_server.py 73~105행의 튜플들을 그대로 복사
    # ("2.3.0", "2026-04-25", [...]), ... ("1.0.0", "2025-12-03", [...])
]


def parse_change(change):
    """'[태그] 내용' 형식이면 (태그, 내용), 아니면 (None, 원문) 반환."""
    if change.startswith("[") and "]" in change:
        close = change.index("]")
        return change[1:close], change[close + 1:].lstrip()
    return None, change
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m unittest tests.test_changelog -v
```

Expected: `OK` (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/changelog.py tests/test_changelog.py
git commit -m "feat: changelog 데이터 분리 및 태그 파서 추가"
```

---

### Task 4: app/config.py — Config 클래스 (TDD)

**Files:**
- Create: `src/app/config.py`
- Test: `src/tests/test_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/tests/test_config.py`:

```python
# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest

from app import DEFAULT_PORT
from app.config import Config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.path)  # 없는 파일에서 시작

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_missing_file_returns_defaults(self):
        config = Config(self.path)
        self.assertIsNone(config.get("printer"))
        self.assertEqual(config.get("kiosk_zoom", 100), 100)

    def test_set_persists_to_disk(self):
        config = Config(self.path)
        config.set("printer", "TestPrinter")
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["printer"], "TestPrinter")
        # 새 인스턴스로 다시 읽어도 유지
        self.assertEqual(Config(self.path).get("printer"), "TestPrinter")

    def test_corrupt_file_treated_as_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{invalid json")
        config = Config(self.path)
        self.assertIsNone(config.get("printer"))

    def test_non_dict_json_treated_as_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('["list"]')
        self.assertIsNone(Config(self.path).get("printer"))

    def test_port_default(self):
        self.assertEqual(Config(self.path).port, DEFAULT_PORT)

    def test_port_valid(self):
        config = Config(self.path)
        config.set("port", 9000)
        self.assertEqual(config.port, 9000)

    def test_port_out_of_range_falls_back(self):
        config = Config(self.path)
        config.set("port", 80)
        self.assertEqual(config.port, DEFAULT_PORT)
        config.set("port", "abc")
        self.assertEqual(config.port, DEFAULT_PORT)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

```bash
python3 -m unittest tests.test_config -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: `src/app/config.py` 구현**

```python
# -*- coding: utf-8 -*-
"""config.json 로드/저장 일원화. 스레드 안전(Lock)."""
import json
import logging
import os
import sys
import threading

from . import DEFAULT_PORT, PORT_MIN, PORT_MAX

logger = logging.getLogger(__name__)


def default_config_path():
    """exe 또는 스크립트와 같은 디렉토리의 config.json 경로."""
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "config.json")


class Config:
    def __init__(self, path=None):
        self.path = path or default_config_path()
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            logger.warning("config.json 최상위가 객체가 아니어서 무시합니다: %r", type(data).__name__)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("config.json 로드 실패: %s", e)
        return {}

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        """값을 설정하고 즉시 디스크에 저장한다."""
        with self._lock:
            self._data[key] = value
            self._save_locked()

    def _save_locked(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("config.json 저장 실패: %s", e)

    @property
    def port(self):
        """검증된 포트 값. 범위 밖/비정수면 DEFAULT_PORT."""
        try:
            value = int(self.get("port", DEFAULT_PORT))
            if PORT_MIN <= value <= PORT_MAX:
                return value
        except (TypeError, ValueError):
            pass
        return DEFAULT_PORT


_instance = None


def get_config():
    """공유 Config 싱글턴 (GUI·API가 동일 인스턴스 사용)."""
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m unittest tests.test_config -v
```

Expected: `OK` (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: 스레드 안전 Config 클래스 (config.json 일원화)"
```

---

### Task 5: app/jobs.py — 인쇄 작업 큐 (TDD)

**Files:**
- Create: `src/app/jobs.py`
- Test: `src/tests/test_jobs.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`src/tests/test_jobs.py`:

```python
# -*- coding: utf-8 -*-
import os
import tempfile
import time
import unittest

from app.jobs import PrintJobQueue, QUEUED, PRINTING, DONE, ERROR


def make_temp_file():
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    return path


class PrintJobQueueTest(unittest.TestCase):
    def test_submit_returns_id_with_queued_status(self):
        q = PrintJobQueue(print_func=lambda path, printer: None)
        path = make_temp_file()
        try:
            job_id = q.submit(path, "P1", filename="a.png")
            job = q.get_job(job_id)
            self.assertEqual(job["status"], QUEUED)
            self.assertEqual(job["printer"], "P1")
            self.assertEqual(job["file"], "a.png")
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_unknown_job_returns_none(self):
        q = PrintJobQueue(print_func=lambda path, printer: None)
        self.assertIsNone(q.get_job("nope"))

    def test_process_success_sets_done_and_removes_temp(self):
        calls = []
        q = PrintJobQueue(print_func=lambda path, printer: calls.append((path, printer)))
        path = make_temp_file()
        job_id = q.submit(path, "P1")
        q._process(*q._queue.get_nowait())
        self.assertEqual(q.get_job(job_id)["status"], DONE)
        self.assertEqual(calls, [(path, "P1")])
        self.assertFalse(os.path.exists(path))

    def test_process_error_sets_error_and_removes_temp(self):
        def boom(path, printer):
            raise RuntimeError("printer on fire")

        q = PrintJobQueue(print_func=boom)
        path = make_temp_file()
        job_id = q.submit(path, "P1")
        q._process(*q._queue.get_nowait())
        job = q.get_job(job_id)
        self.assertEqual(job["status"], ERROR)
        self.assertIn("printer on fire", job["error"])
        self.assertFalse(os.path.exists(path))

    def test_finished_jobs_trimmed_to_max(self):
        q = PrintJobQueue(print_func=lambda path, printer: None, max_finished=2)
        ids = []
        for _ in range(3):
            path = make_temp_file()
            ids.append(q.submit(path, "P1"))
            q._process(*q._queue.get_nowait())
        self.assertIsNone(q.get_job(ids[0]))          # 가장 오래된 완료 작업은 제거
        self.assertEqual(q.get_job(ids[1])["status"], DONE)
        self.assertEqual(q.get_job(ids[2])["status"], DONE)

    def test_worker_thread_processes_jobs(self):
        q = PrintJobQueue(print_func=lambda path, printer: None)
        q.start()
        path = make_temp_file()
        job_id = q.submit(path, "P1")
        deadline = time.time() + 5
        while time.time() < deadline:
            if q.get_job(job_id)["status"] == DONE:
                break
            time.sleep(0.05)
        self.assertEqual(q.get_job(job_id)["status"], DONE)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

```bash
python3 -m unittest tests.test_jobs -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.jobs'`

- [ ] **Step 3: `src/app/jobs.py` 구현**

```python
# -*- coding: utf-8 -*-
"""인쇄 작업을 순차 처리하는 워커 스레드 큐.

print_func(path, printer)를 주입받으므로 win32 없이도 테스트 가능하다.
"""
import logging
import os
import queue
import threading
import uuid
from collections import OrderedDict

logger = logging.getLogger(__name__)

QUEUED = "queued"
PRINTING = "printing"
DONE = "done"
ERROR = "error"


class PrintJobQueue:
    def __init__(self, print_func, max_finished=100):
        self._print_func = print_func
        self._max_finished = max_finished
        self._queue = queue.Queue()
        self._jobs = OrderedDict()   # job_id -> dict
        self._lock = threading.Lock()
        self._thread = None

    def start(self):
        """워커 스레드 기동 (여러 번 호출해도 안전)."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def submit(self, path, printer, filename=""):
        """작업을 큐에 넣고 job_id를 반환한다."""
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": QUEUED,
                "file": filename,
                "printer": printer,
                "error": None,
            }
        self._queue.put((job_id, path, printer))
        return job_id

    def get_job(self, job_id):
        """작업 상태 사본 반환. 없으면 None."""
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _set_status(self, job_id, status, error=None):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job["status"] = status
                job["error"] = error
            if status in (DONE, ERROR):
                self._trim_locked()

    def _trim_locked(self):
        finished = [jid for jid, j in self._jobs.items() if j["status"] in (DONE, ERROR)]
        excess = len(finished) - self._max_finished
        for jid in finished[:excess] if excess > 0 else []:
            del self._jobs[jid]

    def _process(self, job_id, path, printer):
        """단일 작업 처리. 임시 파일은 성공/실패와 무관하게 삭제한다."""
        self._set_status(job_id, PRINTING)
        try:
            self._print_func(path, printer)
            self._set_status(job_id, DONE)
        except Exception as e:
            logger.warning("인쇄 실패 (job %s, printer %s): %s", job_id, printer, e)
            self._set_status(job_id, ERROR, str(e))
        finally:
            try:
                os.remove(path)
            except OSError as e:
                logger.warning("임시 파일 삭제 실패: %s", e)

    def _worker(self):
        while True:
            job_id, path, printer = self._queue.get()
            try:
                self._process(job_id, path, printer)
            finally:
                self._queue.task_done()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python3 -m unittest tests.test_jobs -v
```

Expected: `OK` (6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/jobs.py tests/test_jobs.py
git commit -m "feat: 인쇄 작업 큐 (워커 스레드, job 상태 추적, 임시파일 정리 보장)"
```

---

### Task 6: app/autostart.py + app/kiosk.py — 코드 이동

**Files:**
- Create: `src/app/autostart.py`
- Create: `src/app/kiosk.py`

win32/GUI를 실행할 수 없는 환경이므로 이 두 모듈은 이동 + 로깅 보강만 하고, 검증은 `py_compile`과 Windows 스모크 테스트로 한다.

- [ ] **Step 1: `src/app/autostart.py` 작성**

`printer_server.py` 160–198행(`get_exe_path`, `set_auto_start`, `is_auto_start_enabled`)을 옮긴다. 레지스트리 상수는 이 모듈이 소유한다. 동작(경로 인용 방식 포함)은 변경하지 않는다.

```python
# -*- coding: utf-8 -*-
"""Windows 시작 시 자동 실행 (HKCU Run 레지스트리). Windows 전용."""
import logging
import os
import sys
import winreg

logger = logging.getLogger(__name__)

REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "코어닷투데이 프린터서버"


def get_exe_path():
    """실행 파일 경로 반환 (.py 실행 시 pythonw.exe 경로 포함)."""
    exe = os.path.abspath(sys.argv[0])
    if exe.lower().endswith(".py"):
        python = sys.executable
        pythonw = python.replace("python.exe", "pythonw.exe")
        if os.path.exists(pythonw):
            return f'{pythonw}" "{exe}'
        return f'{python}" "{exe}'
    return exe


def set_auto_start(enabled):
    """자동 실행 등록/해제. (성공 여부, 오류 메시지) 반환."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, f'"{get_exe_path()}"')
        else:
            try:
                winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True, None
    except Exception as e:
        logger.warning("자동 실행 레지스트리 변경 실패: %s", e)
        return False, str(e)


def is_auto_start_enabled():
    """레지스트리에 자동 실행이 등록되어 있는지 확인."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False
```

- [ ] **Step 2: `src/app/kiosk.py` 작성**

`printer_server.py` 204–239행(`find_chrome`, `open_chrome_kiosk`)과 `/close-kiosk` 엔드포인트(417–429행)의 종료 로직을 옮긴다. 프로세스 참조를 이 모듈이 소유한다.

```python
# -*- coding: utf-8 -*-
"""Chrome 키오스크(풀스크린) 모드 실행/종료."""
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

_kiosk_process = None


def find_chrome():
    """Windows에서 Chrome 실행 파일 경로 탐색. 없으면 None."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def open_kiosk(url, zoom=100):
    """Chrome을 키오스크 모드로 실행. (성공 여부, 오류 메시지) 반환."""
    global _kiosk_process
    chrome = find_chrome()
    if not chrome:
        return False, "Chrome을 찾을 수 없습니다. Chrome이 설치되어 있는지 확인해주세요."
    try:
        # 별도 사용자 데이터 디렉토리로 독립 인스턴스 실행 (기존 크롬과 충돌 방지)
        kiosk_data_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "CoreDotKiosk", "ChromeData"
        )
        _kiosk_process = subprocess.Popen([
            chrome,
            "--kiosk",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={kiosk_data_dir}",
            f"--force-device-scale-factor={zoom / 100.0}",
            url,
        ])
        return True, None
    except Exception as e:
        logger.warning("Chrome 키오스크 실행 실패: %s", e)
        return False, str(e)


def close_kiosk():
    """키오스크 Chrome 종료. 상태 문자열("closed"/"no_process"/"error")과 오류 메시지 반환."""
    global _kiosk_process
    if _kiosk_process is None:
        return "no_process", None
    try:
        _kiosk_process.terminate()
        return "closed", None
    except Exception as e:
        logger.warning("키오스크 종료 실패: %s", e)
        return "error", str(e)
    finally:
        _kiosk_process = None
```

- [ ] **Step 3: 문법 검증 (kiosk만 — autostart는 winreg라 WSL에서 import 불가, py_compile은 가능)**

```bash
python3 -m py_compile app/autostart.py app/kiosk.py && python3 -c "from app import kiosk; print(kiosk.find_chrome())"
```

Expected: 에러 없음, `None` 출력(WSL에는 Chrome 없음).

- [ ] **Step 4: Commit**

```bash
git add app/autostart.py app/kiosk.py
git commit -m "refactor: 자동실행/키오스크 모듈 분리"
```

---

### Task 7: app/printing.py — win32 인쇄 (DC 정리 보강)

**Files:**
- Create: `src/app/printing.py`

- [ ] **Step 1: `src/app/printing.py` 작성**

`printer_server.py` 258–341행(프린터 열거·상태)과 343–372행(`print_without_margins`)을 옮기되, `print_without_margins`에 `try/finally` 정리와 `AbortDoc`를 추가하고 `printer_exists`를 신설한다. `_PRINTER_STATUS_FLAGS` 리스트(292–315행)와 `_PRINTER_ATTRIBUTE_WORK_OFFLINE`(317행)은 그대로 복사한다.

```python
# -*- coding: utf-8 -*-
"""Windows 프린터 열거·상태 조회·여백 없는 인쇄. Windows 전용."""
import logging
import os

import win32print
import win32ui
from PIL import Image, ImageWin

logger = logging.getLogger(__name__)


def get_default_printer():
    """Windows 시스템 기본 프린터 이름. 없으면 None."""
    try:
        return win32print.GetDefaultPrinter()
    except Exception as e:
        logger.debug("기본 프린터 조회 실패: %s", e)
        return None


def get_available_printers():
    """설치된 모든 프린터 목록 [{name, is_default}]."""
    printers = []
    try:
        printer_enum = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        default_printer = get_default_printer()
        for printer in printer_enum:
            printers.append({
                "name": printer[2],
                "is_default": printer[2] == default_printer,
            })
    except Exception as e:
        logger.warning("프린터 목록 조회 실패: %s", e)
    return printers


def printer_exists(name):
    """해당 이름의 프린터가 설치되어 있는지 확인."""
    return any(p["name"] == name for p in get_available_printers())


# 프린터 상태 비트 → (한글 라벨, 색상 키). winspool.h PRINTER_STATUS_* 값
_PRINTER_STATUS_FLAGS = [
    # printer_server.py 292~315행의 튜플들을 그대로 복사
]
# "오프라인으로 사용" — 사용자가 명시적으로 끈 경우 (PRINTER_ATTRIBUTE_WORK_OFFLINE)
_PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x00000400


def get_printer_status(name):
    """프린터 상태를 (라벨, 색상키) 튜플로 반환. 색상 키: green/orange/red/gray"""
    try:
        h = win32print.OpenPrinter(name)
        try:
            info = win32print.GetPrinter(h, 2)
        finally:
            win32print.ClosePrinter(h)
    except Exception:
        return ("조회 실패", "gray")

    if info.get('Attributes', 0) & _PRINTER_ATTRIBUTE_WORK_OFFLINE:
        return ("오프라인으로 사용", "red")

    status = info.get('Status', 0)
    if status == 0:
        return ("준비됨", "green")

    for bit, label, color in _PRINTER_STATUS_FLAGS:
        if status & bit:
            return (label, color)

    return ("알 수 없음", "gray")


def print_without_margins(path, printer):
    """여백 없이 이미지 인쇄. 실패 시 예외를 던지고 DC를 정리한다."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    image = Image.open(path)
    try:
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer)
        doc_started = False
        try:
            printable_area = hdc.GetDeviceCaps(110), hdc.GetDeviceCaps(111)
            printer_margins = (hdc.GetDeviceCaps(112), hdc.GetDeviceCaps(113))

            hdc.StartDoc(path)
            doc_started = True
            hdc.StartPage()

            dib = ImageWin.Dib(image)
            dib.draw(hdc.GetHandleOutput(), (
                -printer_margins[0],
                -printer_margins[1],
                printable_area[0] - printer_margins[0],
                printable_area[1] - printer_margins[1],
            ))

            hdc.EndPage()
            hdc.EndDoc()
            doc_started = False
        except Exception:
            if doc_started:
                try:
                    hdc.AbortDoc()
                except Exception as e:
                    logger.debug("AbortDoc 실패: %s", e)
            raise
        finally:
            hdc.DeleteDC()
    finally:
        image.close()   # 임시 파일 핸들 해제 (삭제가 실패하지 않도록)
```

주의: `_PRINTER_STATUS_FLAGS`는 반드시 원본 292–315행의 22개 튜플 전체를 복사할 것.

- [ ] **Step 2: 문법 검증**

```bash
python3 -m py_compile app/printing.py
```

Expected: 에러 없음.

- [ ] **Step 3: Commit**

```bash
git add app/printing.py
git commit -m "refactor: win32 인쇄 모듈 분리 + DC 정리/AbortDoc 보강"
```

---

### Task 8: app/api.py — 검증 + job 추적 엔드포인트

**Files:**
- Create: `src/app/api.py`

- [ ] **Step 1: `src/app/api.py` 작성 (전체)**

```python
# -*- coding: utf-8 -*-
"""FastAPI 앱 및 엔드포인트."""
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from . import kiosk, printing
from .jobs import PrintJobQueue

logger = logging.getLogger(__name__)

# GUI에서 선택된 프린터 (GUI 스레드가 설정, API가 참조)
_selected_printer: Optional[str] = None


def set_selected_printer(name):
    global _selected_printer
    _selected_printer = name or None


def get_selected_printer():
    return _selected_printer


jobs = PrintJobQueue(print_func=printing.print_without_margins)

api = FastAPI(title="프린터 API 서버")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.get("/printers")
async def list_printers():
    """설치된 프린터 목록 조회"""
    printers = printing.get_available_printers()
    return {
        "printers": printers,
        "default": printing.get_default_printer(),
        "count": len(printers),
    }


@api.post("/print-image")
async def print_image(
    file: UploadFile = File(...),
    printer: Optional[str] = Form(None),
):
    """이미지를 지정된 프린터로 인쇄 (여백 없이).

    우선순위: 요청 파라미터 > GUI 선택 > Windows 시스템 기본.
    프린터 존재·이미지 유효성을 사전 검증하고, 실패는 즉시 4xx로 반환한다.
    """
    target_printer = printer or get_selected_printer() or printing.get_default_printer()
    if not target_printer:
        raise HTTPException(status_code=400, detail="사용 가능한 프린터가 없습니다.")
    if not printing.printer_exists(target_printer):
        raise HTTPException(status_code=400, detail=f"프린터를 찾을 수 없습니다: {target_printer}")

    suffix = os.path.splitext(file.filename or "")[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        with Image.open(tmp_path) as img:
            img.verify()
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError as e:
            logger.warning("임시 파일 삭제 실패: %s", e)
        raise HTTPException(status_code=400, detail="유효한 이미지 파일이 아닙니다.")

    job_id = jobs.submit(tmp_path, target_printer, filename=file.filename or "")
    return {
        "status": "queued",
        "file": file.filename,
        "printer": target_printer,
        "job_id": job_id,
    }


@api.get("/print-jobs/{job_id}")
async def get_print_job(job_id: str):
    """인쇄 작업 상태 조회 (queued/printing/done/error)"""
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return job


@api.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {"status": "ok"}


@api.post("/close-kiosk")
async def close_kiosk():
    """키오스크 Chrome 프로세스 종료"""
    status, message = kiosk.close_kiosk()
    result = {"status": status}
    if message:
        result["message"] = message
    return result


@api.post("/shutdown")
async def shutdown_windows():
    """Windows 시스템 종료"""
    try:
        subprocess.Popen(["shutdown", "/s", "/t", "5"], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"status": "ok", "message": "5초 후 시스템이 종료됩니다."}
    except Exception as e:
        logger.warning("시스템 종료 명령 실패: %s", e)
        return {"status": "error", "message": str(e)}
```

호환성 메모: `/print-image` 성공 응답의 기존 필드(`status`/`file`/`printer`)는 유지되고 `job_id`가 추가된다. `/printers`의 이전 `error` 필드는 실패 시에도 목록이 빈 배열로 반환되므로 제거해도 동작 호환(기존 클라이언트는 `printers` 배열만 사용).

- [ ] **Step 2: 문법 검증**

```bash
python3 -m py_compile app/api.py
```

Expected: 에러 없음.

- [ ] **Step 3: Commit**

```bash
git add app/api.py
git commit -m "feat: API 사전검증 + job_id 반환 + /print-jobs/{id} 상태 조회"
```

---

### Task 9: app/server.py — 시작 판정·중지 신뢰성·/health 로그 필터

**Files:**
- Create: `src/app/server.py`

- [ ] **Step 1: `src/app/server.py` 작성 (전체)**

```python
# -*- coding: utf-8 -*-
"""백그라운드 uvicorn 서버 래퍼."""
import logging
import threading

import uvicorn

from . import DEFAULT_PORT
from .api import api

logger = logging.getLogger(__name__)


class HealthAccessFilter(logging.Filter):
    """/health 요청은 access 로그에서 제외 (폴링 스팸 방지)."""
    def filter(self, record):
        return "/health" not in record.getMessage()


class QueueLogHandler(logging.Handler):
    """logging 핸들러 — 로그를 콜백으로 전달"""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        try:
            self.callback(self.format(record) + "\n")
        except Exception:
            pass


class UvicornServer:
    """백그라운드 스레드에서 실행되는 uvicorn 서버."""
    def __init__(self, host="0.0.0.0", port=DEFAULT_PORT, log_callback=None):
        self.host = host
        self.port = port
        self.log_callback = log_callback
        self.server = None
        self.thread = None

    @property
    def started(self):
        """uvicorn이 실제로 리스닝을 시작했는지 여부."""
        return bool(self.server and self.server.started)

    def is_alive(self):
        """서버 스레드가 살아있는지 여부 (바인드 실패 시 False)."""
        return bool(self.thread and self.thread.is_alive())

    def start(self):
        if self.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _setup_log_redirect(self):
        health_filter = HealthAccessFilter()
        logging.getLogger("uvicorn.access").addFilter(health_filter)
        if not self.log_callback:
            return
        handler = QueueLogHandler(self.log_callback)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
            log = logging.getLogger(name)
            log.handlers = [handler]
            log.propagate = False

    def _run(self):
        config = uvicorn.Config(
            api,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=True,
        )
        self.server = uvicorn.Server(config)

        self._setup_log_redirect()
        if self.log_callback:
            self.log_callback(f"Uvicorn running on http://{self.host}:{self.port}\n")

        try:
            self.server.run()
        except Exception as e:
            logger.warning("서버 오류: %s", e)
            if self.log_callback:
                self.log_callback(f"서버 오류: {e}\n")

    def stop(self, timeout=3.0):
        """종료 요청 후 스레드 종료를 기다린다 (최대 timeout초)."""
        if self.server:
            self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout)
```

- [ ] **Step 2: 문법 검증**

```bash
python3 -m py_compile app/server.py
```

Expected: 에러 없음.

- [ ] **Step 3: Commit**

```bash
git add app/server.py
git commit -m "feat: 서버 시작 판정(started)·join 기반 중지·/health 로그 필터"
```

---

### Task 10: app/gui.py — GUI 이동 + 반응성·자동갱신·링버퍼·접속범위

**Files:**
- Create: `src/app/gui.py`
- Reference: `src/printer_server.py:516-1408` (이동 원본)

가장 큰 작업. `printer_server.py`의 `create_labeled_frame`(516–521행), `PrinterAPILauncher`(524–1408행)를 `app/gui.py`로 옮기면서 아래 수정을 적용한다. **명시되지 않은 메서드/위젯 코드는 원본 그대로 복사한다** (특히 `setup_ui`의 위젯 생성부, `_show_changelog`, 키오스크 URL 메뉴 관련 메서드의 UI 부분).

- [ ] **Step 1: 파일 헤더와 모듈 상수 작성**

```python
# -*- coding: utf-8 -*-
"""customtkinter GUI 런처."""
import logging
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from . import APP_COPYRIGHT, APP_NAME, DEFAULT_PORT, HELP_URL, PORT_MAX, PORT_MIN, VERSION
from . import autostart, kiosk
from .api import jobs, set_selected_printer
from .changelog import CHANGELOG, parse_change
from .config import get_config
from .printing import get_available_printers, get_default_printer, get_printer_status
from .server import UvicornServer

logger = logging.getLogger(__name__)

# 콤보박스 표시용: "프린터이름  ·  상태" 구분자
STATUS_SEP = "  ·  "
# 상태 색상 키 → CTk 색상
STATUS_COLORS = {
    "green": "#4CAF50",
    "orange": "#FFC107",
    "red": "#f44336",
    "gray": "gray",
}

MAX_LOG_LINES = 1000          # GUI 로그 최대 줄 수 (링 버퍼)
STATUS_REFRESH_MS = 30_000    # 프린터 상태 자동 갱신 주기
SERVER_POLL_MS = 200          # 서버 시작 판정 폴링 주기
SERVER_POLL_MAX = 25          # 최대 폴링 횟수 (약 5초)
```

`create_labeled_frame`은 원본 그대로 복사.

- [ ] **Step 2: `__init__` 수정**

원본 525–575행을 복사하되 다음을 반영한 전체 코드:

```python
class PrinterAPILauncher:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config = get_config()

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME}  v{VERSION}")
        self.root.geometry("680x800")
        self.root.resizable(False, False)

        # 아이콘 설정 — 원본 535~543행 그대로 복사하되 except: pass를
        # except Exception as e: logger.debug("아이콘 로드 실패: %s", e) 로 변경

        # 서버 관련 변수
        self.server = None
        self.is_running = False
        self.log_queue = queue.Queue()
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.allow_external_var = tk.BooleanVar(value=True)

        # 프린터 관련 변수
        self.available_printers = []
        self.selected_printer = tk.StringVar()   # raw 이름만 저장 (콤보 표시값 아님)
        self._printer_statuses = {}              # name → (라벨, 색상키)
        self._printers_loading = False           # 백그라운드 조회 재진입 방지
        self.auto_start_var = tk.BooleanVar(value=False)

        # 키오스크 관련 변수
        self.kiosk_url_var = tk.StringVar()
        self.kiosk_auto_open_var = tk.BooleanVar(value=False)
        self.kiosk_zoom_var = tk.StringVar(value="100")
        self._saved_urls = []

        # UI 초기화
        self.setup_ui()

        # 인쇄 작업 워커 기동
        jobs.start()

        # 프린터 목록 로드 (백그라운드) 후 설정 적용
        self.load_printers(then=self._apply_saved_config)

        # 프린터 상태 자동 갱신 타이머
        self.root.after(STATUS_REFRESH_MS, self._auto_refresh_printers)

        # 종료 시 정리
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
```

- [ ] **Step 3: 로그 링 버퍼 메서드 추가 + 호출부 일괄 치환**

새 메서드:

```python
    def _append_log(self, text):
        """로그 창에 텍스트 추가. MAX_LOG_LINES를 넘으면 앞에서 삭제 (링 버퍼)."""
        self.log_text.insert(tk.END, text)
        try:
            total = int(self.log_text.index("end-1c").split(".")[0])
            if total > MAX_LOG_LINES:
                self.log_text.delete("1.0", f"{total - MAX_LOG_LINES + 1}.0")
        except Exception as e:
            logger.debug("로그 버퍼 정리 실패: %s", e)
        self.log_text.see(tk.END)
```

일괄 치환: 원본 전체에서 아래 패턴의 연속 2줄

```python
self.log_text.insert(tk.END, X)
self.log_text.see(tk.END)
```

을 `self._append_log(X)` 한 줄로 치환한다. `see` 없이 `insert`만 있는 곳(연속 insert 블록)도 각 `insert(tk.END, X)`를 `self._append_log(X)`로 바꾼다. `update_log`의 본문도 `self._append_log(line)`을 사용:

```python
    def update_log(self):
        """큐에서 로그를 가져와 UI 업데이트"""
        try:
            while True:
                self._append_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self.update_log)
```

- [ ] **Step 4: 프린터 조회 백그라운드화 + 자동 갱신**

원본 `load_printers`(581–620행)를 다음 3개 메서드로 교체:

```python
    def load_printers(self, then=None):
        """프린터 목록·상태를 백그라운드 스레드에서 조회 (GUI 블로킹 방지).

        then: 조회 완료 후 GUI 스레드에서 실행할 콜백 (설정 적용 등).
        """
        if self._printers_loading:
            return
        self._printers_loading = True

        def worker():
            try:
                printers = get_available_printers()
                default = get_default_printer()
                statuses = {p["name"]: get_printer_status(p["name"]) for p in printers}
            except Exception as e:
                logger.warning("프린터 조회 실패: %s", e)
                printers, default, statuses = [], None, {}
            self.root.after(0, lambda: self._apply_printer_data(printers, default, statuses, then))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_printer_data(self, printers, default_printer, statuses, then=None):
        """백그라운드 조회 결과를 GUI에 반영 (GUI 스레드에서 실행)."""
        self._printers_loading = False
        self.available_printers = [p["name"] for p in printers]
        self._printer_statuses = statuses

        display_values = [
            f"{name}{STATUS_SEP}{statuses.get(name, ('', ''))[0]}"
            for name in self.available_printers
        ]

        # 현재 선택 보존: 목록에서 사라졌으면 기본 프린터로 대체
        current = self.selected_printer.get()
        if current not in self.available_printers:
            current = default_printer if default_printer in self.available_printers else ""
            self.selected_printer.set(current)

        # 모듈 상태 반영 (API 엔드포인트가 참조)
        set_selected_printer(current)

        self.printer_combo.configure(values=display_values or [""])
        self._set_combo_display(current)
        self._update_status_label()

        if not self.available_printers:
            self._append_log("경고: 설치된 프린터가 없습니다.\n")
        else:
            names = ", ".join(self.available_printers)
            self._append_log(f"프린터 {len(self.available_printers)}개 감지: {names}\n")

        if then:
            then()

    def _auto_refresh_printers(self):
        """주기적 프린터 상태 갱신 (창이 떠 있는 동안)."""
        self.load_printers()
        self.root.after(STATUS_REFRESH_MS, self._auto_refresh_printers)
```

`refresh_printers`는 유지하되 본문을 `self._append_log(...)` + `self.load_printers()`로. `_set_combo_display`, `_update_status_label`은 원본 그대로 복사.

- [ ] **Step 5: 서버 수명주기 메서드 교체**

원본 `start_server`/`_check_server_started`/`stop_server`/`restart_server`/`on_closing`(955–1032, 1396–1405행)을 다음으로 교체:

```python
    def start_server(self):
        if self.is_running:
            return

        self._append_log(f"\n{'=' * 50}\n서버를 시작합니다...\n")

        port = self.config.port
        host = "0.0.0.0" if self.config.get("allow_external", True) else "127.0.0.1"
        self.url_label.configure(text=f"http://localhost:{port}")
        self.server = UvicornServer(host=host, port=port, log_callback=self.log)
        self.server.start()
        self.is_running = True
        self.update_ui_state(running=True)
        self.root.after(SERVER_POLL_MS, lambda: self._poll_server_started(0))

    def _poll_server_started(self, attempts):
        """uvicorn started 속성을 폴링하여 시작 성공/실패를 판정."""
        if not self.is_running or self.server is None:
            return
        if self.server.started:
            self._append_log("\n✓ 서버가 성공적으로 시작되었습니다!\n")
            if self.kiosk_auto_open_var.get() and self.kiosk_url_var.get().strip():
                self.root.after(500, self._open_kiosk_chrome)
            return
        if self.server.is_alive() and attempts < SERVER_POLL_MAX:
            self.root.after(SERVER_POLL_MS, lambda: self._poll_server_started(attempts + 1))
            return

        # 스레드 사망(포트 바인드 실패 등) 또는 타임아웃
        port = self.server.port
        self._append_log(f"\n✗ 서버 시작 실패 (포트 {port})\n")
        self.server.stop()
        self.server = None
        self.is_running = False
        self.update_ui_state(running=False)
        messagebox.showerror(
            "서버 시작 실패",
            f"포트 {port}에서 서버를 시작하지 못했습니다.\n\n"
            f"다른 프로그램이 해당 포트를 사용 중일 수 있습니다.\n"
            f"포트를 변경한 후 다시 시도해주세요."
        )

    def stop_server(self):
        if not self.is_running:
            return

        self._append_log("\n서버를 중지합니다...\n")
        if self.server:
            self.server.stop()   # should_exit 후 join(3초) — 포트 해제 보장
        self.server = None
        self.is_running = False
        self._append_log(f"서버가 중지되었습니다.\n{'=' * 50}\n")
        self.update_ui_state(running=False)

    def restart_server(self):
        self._append_log("\n서버를 재시작합니다...\n")
        self.stop_server()
        self.start_server()

    def on_closing(self):
        """프로그램 종료 시 처리"""
        if self.is_running:
            if not messagebox.askyesno("종료", "서버가 실행 중입니다. 서버를 중지하고 종료하시겠습니까?"):
                return
            self.stop_server()
        self.root.destroy()
```

`update_ui_state`는 원본 그대로 복사하되 첫 줄을 `port = self.config.port`로 변경.

- [ ] **Step 6: 외부 접속 허용 체크박스 추가**

`setup_ui`의 자동 실행 체크박스(원본 753–772행) 아래, 같은 `auto_start_frame`에 추가:

```python
        self.allow_external_check = ctk.CTkCheckBox(
            auto_start_frame,
            text="외부 접속 허용 (같은 네트워크)",
            variable=self.allow_external_var,
            command=self._on_allow_external_changed,
            font=ctk.CTkFont(family="맑은 고딕", size=12)
        )
        self.allow_external_check.pack(side='left', padx=(20, 0))
```

핸들러 신설:

```python
    def _on_allow_external_changed(self):
        """외부 접속 허용 체크박스 변경 시 호출. 서버 재시작 시 적용."""
        allow = self.allow_external_var.get()
        self.config.set("allow_external", allow)
        state = "허용" if allow else "차단 (같은 PC만)"
        suffix = " — 서버 재시작 후 적용됩니다." if self.is_running else ""
        self._append_log(f"외부 접속 {state}{suffix}\n")
        if self.is_running:
            messagebox.showinfo("알림", f"외부 접속이 {state}으로 저장되었습니다.\n서버 재시작 후 적용됩니다.")
```

- [ ] **Step 7: Config 사용으로 전환 (설정 핸들러들)**

원본에서 `load_config()`/`save_config()`를 쓰는 각 메서드를 `self.config.get`/`self.config.set`으로 바꾼다. 변경되는 메서드 전체 코드:

```python
    def _apply_saved_config(self):
        """저장된 설정을 로드하여 적용 (프린터 목록 로드 완료 후 호출)."""
        saved_printer = self.config.get("printer", "")
        auto_start = self.config.get("auto_start", False)

        # 저장된 포트 복원 + URL 라벨 갱신
        port = self.config.port
        self.port_var.set(str(port))
        self.url_label.configure(text=f"http://localhost:{port}")

        # 외부 접속 허용 상태 복원
        self.allow_external_var.set(self.config.get("allow_external", True))

        # 저장된 프린터가 현재 설치된 목록에 있으면 선택
        if saved_printer and saved_printer in self.available_printers:
            self.selected_printer.set(saved_printer)
            self._set_combo_display(saved_printer)
            self._append_log(f"저장된 프린터 선택: {saved_printer}\n")

        # 현재 선택을 모듈 상태 + 상태 라벨에 반영
        set_selected_printer(self.selected_printer.get())
        self._update_status_label()

        # 자동 실행 상태 반영
        self.auto_start_var.set(auto_start and autostart.is_auto_start_enabled())
        self._update_auto_start_info()

        # 키오스크 설정 로드
        self._saved_urls = self.config.get("saved_urls", [])
        self._update_kiosk_url_menu()
        kiosk_url = self.config.get("kiosk_url", "")
        if kiosk_url:
            self.kiosk_url_var.set(kiosk_url)
        self.kiosk_auto_open_var.set(self.config.get("kiosk_auto_open", False))
        self.kiosk_zoom_var.set(str(self.config.get("kiosk_zoom", 100)))

        # 자동 실행이면 서버 자동 시작
        if self.auto_start_var.get():
            self._append_log("자동 실행 모드: 서버를 시작합니다...\n")
            self.root.after(500, self.start_server)

    def _on_auto_start_changed(self):
        """자동 실행 체크박스 변경 시 호출"""
        enabled = self.auto_start_var.get()
        printer = self.selected_printer.get()

        if enabled and not printer:
            messagebox.showwarning("경고", "먼저 프린터를 선택해주세요.")
            self.auto_start_var.set(False)
            return

        success, error = autostart.set_auto_start(enabled)
        if not success:
            messagebox.showerror("자동 실행 오류", f"레지스트리 등록에 실패했습니다.\n\n{error}")
            self.auto_start_var.set(False)
            return

        self.config.set("auto_start", enabled)
        if enabled:
            self.config.set("printer", printer)

        self._update_auto_start_info()
        if enabled:
            self._append_log(f"자동 실행 설정됨 (프린터: {printer})\n")
        else:
            self._append_log("자동 실행 해제됨\n")

    def _update_auto_start_info(self):
        """자동 실행 상태 라벨 업데이트"""
        if self.auto_start_var.get():
            self.auto_start_info.configure(text=f"(프린터: {self.config.get('printer', '')})")
        else:
            self.auto_start_info.configure(text="")

    def _on_printer_changed(self, display_value=None):
        """프린터 선택이 변경될 때 호출. 콤보는 '이름 · 상태' display를 전달"""
        if display_value and STATUS_SEP in display_value:
            printer = display_value.split(STATUS_SEP)[0]
        else:
            printer = display_value or ""

        if not printer or printer not in self.available_printers:
            return

        self.selected_printer.set(printer)
        set_selected_printer(printer)
        self._update_status_label()
        self.config.set("printer", printer)

        if self.auto_start_var.get():
            autostart.set_auto_start(True)
            self._update_auto_start_info()
            self._append_log(f"자동 실행 프린터 변경: {printer}\n")
        else:
            self._append_log(f"프린터 선택: {printer}\n")

    def _save_kiosk_url(self):
        """현재 입력된 URL을 저장 목록에 추가"""
        url = self.kiosk_url_var.get().strip()
        if not url:
            messagebox.showwarning("경고", "URL을 입력해주세요.")
            return

        if url not in self._saved_urls:
            self._saved_urls.append(url)
            self.config.set("saved_urls", self._saved_urls)
        self.config.set("kiosk_url", url)

        self._update_kiosk_url_menu()
        self._append_log(f"키오스크 URL 저장됨: {url}\n")

    def _delete_kiosk_url(self):
        """현재 선택된 URL을 저장 목록에서 삭제"""
        url = self.kiosk_url_var.get().strip()
        if not url or url not in self._saved_urls:
            return

        self._saved_urls.remove(url)
        self.config.set("saved_urls", self._saved_urls)
        if self.config.get("kiosk_url") == url:
            new_url = self._saved_urls[0] if self._saved_urls else ""
            self.config.set("kiosk_url", new_url)
        self._update_kiosk_url_menu()
        self.kiosk_url_var.set(self.config.get("kiosk_url", ""))
        self._append_log(f"키오스크 URL 삭제됨: {url}\n")

    def _save_kiosk_zoom(self):
        """확대율 저장"""
        zoom = self.kiosk_zoom_var.get().strip()
        try:
            zoom_val = int(zoom)
            if zoom_val < 50 or zoom_val > 300:
                messagebox.showwarning("경고", "확대율은 50~300 사이로 입력해주세요.")
                return
        except ValueError:
            messagebox.showwarning("경고", "숫자를 입력해주세요.")
            return

        self.config.set("kiosk_zoom", zoom_val)
        self._append_log(f"키오스크 확대율 저장됨: {zoom_val}%\n")

    def _save_port(self):
        """서버 포트 저장 — 다음 서버 시작 시 적용"""
        raw = self.port_var.get().strip()
        try:
            port_val = int(raw)
        except ValueError:
            messagebox.showwarning("경고", "숫자를 입력해주세요.")
            self.port_var.set(str(self.config.port))
            return

        if port_val < PORT_MIN or port_val > PORT_MAX:
            messagebox.showwarning("경고", f"포트는 {PORT_MIN}~{PORT_MAX} 사이로 입력해주세요.")
            self.port_var.set(str(self.config.port))
            return

        self.config.set("port", port_val)
        self.url_label.configure(text=f"http://localhost:{port_val}")

        if self.is_running:
            self._append_log(f"포트 저장됨: {port_val} (재시작 후 적용)\n")
            messagebox.showinfo("알림", f"포트가 {port_val}로 저장되었습니다.\n서버 재시작 후 적용됩니다.")
        else:
            self._append_log(f"포트 저장됨: {port_val}\n")

    def _on_kiosk_auto_open_changed(self):
        """키오스크 자동 열기 체크박스 변경 시 호출"""
        self.config.set("kiosk_auto_open", self.kiosk_auto_open_var.get())

    def _open_kiosk_chrome(self):
        """키오스크 모드로 크롬 열기"""
        url = self.kiosk_url_var.get().strip()
        if not url:
            return
        success, error = kiosk.open_kiosk(url, zoom=self.config.get("kiosk_zoom", 100))
        if success:
            self._append_log(f"크롬 키오스크 모드 열기: {url}\n")
        else:
            self._append_log(f"크롬 열기 실패: {error}\n")
```

- [ ] **Step 8: `_show_changelog`에서 파서 사용**

원본 1356–1374행의 태그 파싱 인라인 코드를 `parse_change` 호출로 교체:

```python
            for change in changes:
                tag, body = parse_change(change)
                if tag in self._CHANGELOG_TAG_COLORS:
                    text.insert(tk.END, "  ")
                    text.insert(tk.END, f"[{tag}]", f"t_{tag}")
                    text.insert(tk.END, f"  {body}\n")
                else:
                    text.insert(tk.END, f"  · {change}\n", "bullet")
```

`_CHANGELOG_TAG_COLORS` 클래스 속성과 `_show_changelog`의 나머지는 원본 그대로 복사. (릴리스 노트 창의 `insert`는 링버퍼 대상이 아님 — `log_text`가 아니므로 치환하지 않는다.)

- [ ] **Step 9: 문법 검증**

```bash
python3 -m py_compile app/gui.py
```

Expected: 에러 없음.

- [ ] **Step 10: Commit**

```bash
git add app/gui.py
git commit -m "refactor: GUI 분리 + 상태조회 백그라운드화·자동갱신·로그 링버퍼·외부접속 설정"
```

---

### Task 11: printer_server.py 진입점 교체

**Files:**
- Modify: `src/printer_server.py` (전체 교체)

- [ ] **Step 1: `src/printer_server.py` 전체를 다음으로 교체**

```python
# -*- coding: utf-8 -*-
"""
프린터 API 서버 - 진입점
본체는 app/ 패키지에 있다. Nuitka onefile 빌드 대상.
"""
import os
import sys
import traceback


def _base_dir():
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def show_startup_error(title, message):
    """시작 시 에러를 사용자에게 보여주는 함수 (GUI 초기화 전에도 동작)"""
    try:
        with open(os.path.join(_base_dir(), "error.log"), "w", encoding="utf-8") as f:
            f.write(f"{title}\n{message}\n")
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox as mb
        root = tk.Tk()
        root.withdraw()
        mb.showerror(title, message)
        root.destroy()
    except Exception:
        pass


def _hide_console():
    """콘솔 창 숨기기 + 작업표시줄 제거 (Nuitka onefile 호환)"""
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def _already_running(port):
    """중복 실행 감지 — /health 응답으로 '우리 서버'인지 식별.

    포트를 쓰는 게 남의 프로세스면 False (GUI를 띄워 포트 변경 가능하게).
    """
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return '"status"' in body and '"ok"' in body
    except Exception:
        return False


if __name__ == "__main__":
    # 작업 디렉토리를 exe가 있는 디렉토리로 변경 (레지스트리 자동 실행 시 CWD가 System32일 수 있음)
    os.chdir(_base_dir())
    _hide_console()

    # stderr를 로그 파일로 리다이렉트 (에러 진단용)
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.path.join(_base_dir(), "error.log"), "w", encoding="utf-8")
    except Exception:
        pass

    try:
        import logging
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

        from tkinter import messagebox
        from app.config import get_config
        from app.gui import PrinterAPILauncher

        port = get_config().port
        if _already_running(port):
            messagebox.showwarning(
                "경고",
                f"프린터 API 서버가 이미 실행 중입니다.\n(포트 {port})"
            )
            sys.exit(0)

        PrinterAPILauncher().run()
    except Exception as e:
        show_startup_error(
            "프린터 서버 실행 오류",
            f"오류: {type(e).__name__}: {e}\n\n"
            f"상세:\n{traceback.format_exc()}\n\n"
            f"이 오류가 계속되면 고객지원에 문의해주세요."
        )
        sys.exit(1)
```

메모: 원본의 모듈 import 실패 팝업(34–124행 try/except)은 `if __name__` 블록의 try/except가 대체한다 — `app.gui` import 시점에 실패해도 `show_startup_error`가 잡는다. `run()` 메서드(`self.root.mainloop()`)는 gui.py의 `PrinterAPILauncher`에 존재해야 한다(Task 10에서 원본 그대로 복사됨).

- [ ] **Step 2: 문법 검증 + 전체 테스트**

```bash
python3 -m py_compile printer_server.py
python3 -m unittest discover -s tests -v
```

Expected: 컴파일 에러 없음, 테스트 전체 `OK` (17 tests).

- [ ] **Step 3: Commit**

```bash
git add printer_server.py
git commit -m "refactor: printer_server.py를 얇은 진입점으로 교체"
```

---

### Task 12: 버전·CHANGELOG·스모크 테스트 문서

**Files:**
- Modify: `src/app/changelog.py` (2.4.0 항목 추가)
- Modify: `CHANGELOG.md` (외부 repo)
- Create: `docs/smoke-test.md` (외부 repo)

- [ ] **Step 1: `src/app/changelog.py`의 `CHANGELOG` 리스트 맨 앞에 추가**

```python
    ("2.4.0", "2026-07-19", [
        "[개선] 프린터 상태 조회를 백그라운드로 이동 — 시작·새로고침 시 화면 멈춤 제거",
        "[추가] 프린터 상태 30초 주기 자동 갱신",
        "[추가] 인쇄 작업 추적 — 응답에 job_id 포함, GET /print-jobs/{job_id} 상태 조회",
        "[개선] 인쇄 요청 사전 검증 — 잘못된 프린터명·이미지 즉시 오류 반환",
        "[추가] 외부 접속 허용/차단 설정 (같은 네트워크 vs 같은 PC만)",
        "[수정] 서버 재시작 시 포트 미해제로 실패하던 문제",
        "[개선] 서버 로그 최근 1,000줄만 유지 (장기 가동 시 메모리 증가 방지)",
        "[변경] 코드 구조를 app/ 패키지로 분리 (동작 동일)",
    ]),
```

- [ ] **Step 2: 테스트 재실행 후 src 커밋**

```bash
python3 -m unittest discover -s tests -v
git add app/changelog.py
git commit -m "chore: v2.4.0 릴리스 노트 추가"
```

Expected: `OK`.

- [ ] **Step 3: 외부 repo의 `CHANGELOG.md` 맨 위(## v2.0.0 앞)에 추가**

```markdown
## v2.4.0 (2026-07-19)

- 프린터 상태 조회 백그라운드화 (시작·새로고침 시 화면 멈춤 제거) + 30초 자동 갱신
- 인쇄 작업 추적: 응답에 `job_id` 포함, `GET /print-jobs/{job_id}` 상태 조회 추가
- 인쇄 요청 사전 검증 (잘못된 프린터명·이미지 즉시 오류 반환)
- 외부 접속 허용/차단 설정 추가 (같은 네트워크 vs 같은 PC만)
- 서버 재시작 안정화, 로그 메모리 증가 방지
- 코드 구조를 app/ 패키지로 분리
```

- [ ] **Step 4: `docs/smoke-test.md` 작성 (외부 repo)**

```markdown
# Windows 스모크 테스트 체크리스트

릴리스 전 Windows 실기에서 확인한다. (`python src/printer_server.py` 또는 빌드된 exe)

## 기동
- [ ] 앱 실행 → 창이 뜨고 프린터 목록·상태(색상 라벨)가 곧 표시된다 (창 멈춤 없음)
- [ ] 앱을 한 번 더 실행 → "이미 실행 중" 경고 후 종료
- [ ] config.json 삭제 후 실행 → 기본값(포트 8000)으로 정상 기동

## 서버
- [ ] 시작 → 상태 표시 초록 "서버 실행 중", 로그에 "성공적으로 시작"
- [ ] `GET /health` → `{"status":"ok"}` (access 로그에 /health 미출력 확인)
- [ ] 중지 → 즉시 "서버 중지됨", 재시작 → 실패 없이 다시 시작
- [ ] 사용 중인 포트로 시작 → 오류 팝업, UI가 '중지됨'으로 복귀
- [ ] 포트 변경 저장 → 재시작 후 새 포트로 접속

## 인쇄 API
- [ ] `POST /print-image` (정상 이미지) → `job_id` 포함 응답, 실제 인쇄됨
- [ ] `GET /print-jobs/{job_id}` → `done`
- [ ] 존재하지 않는 프린터명 지정 → 400 응답
- [ ] 이미지가 아닌 파일 업로드 → 400 응답
- [ ] 프린터 전원 끄고 인쇄 → job 상태 `error` + 오류 메시지, 임시 폴더에 파일 미잔류

## 프린터 상태
- [ ] 프린터 끄기 → 30초 내 상태 라벨이 빨강(오프라인)으로 자동 갱신
- [ ] 새로고침 버튼 → 즉시 갱신, 창 멈춤 없음

## 키오스크
- [ ] URL 저장/선택/삭제 동작
- [ ] "서버 시작 시 크롬 자동 열기" → 시작 시 풀스크린 크롬
- [ ] `POST /close-kiosk` → 크롬 종료
- [ ] 확대율 저장 → 크롬 스케일 반영

## 자동 실행·접속 범위
- [ ] "Windows 시작 시 자동 실행" 켬 → 재부팅 후 자동 기동 + 서버 자동 시작
- [ ] "외부 접속 허용" 끔 + 재시작 → 다른 기기에서 접속 불가, 같은 PC는 가능
- [ ] "외부 접속 허용" 켬 + 재시작 → 같은 네트워크 기기에서 접속 가능

## 장기 가동
- [ ] 서버 로그가 1,000줄 근처에서 더 늘지 않음 (오래 실행 후 확인)

## 릴리스 노트
- [ ] 버전 라벨 클릭 → v2.4.0 항목이 태그 색상과 함께 표시
```

- [ ] **Step 5: 외부 repo 커밋**

```bash
cd /mnt/c/Users/kyunghoon/projects/coredot-printer
git add CHANGELOG.md docs/smoke-test.md
git commit -m "docs: v2.4.0 변경 내역 및 스모크 테스트 체크리스트"
```

---

### Task 13: 최종 검증

- [ ] **Step 1: 전체 테스트 + 전 모듈 컴파일 (src/에서)**

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile printer_server.py app/__init__.py app/changelog.py app/config.py app/jobs.py app/autostart.py app/kiosk.py app/printing.py app/api.py app/server.py app/gui.py
```

Expected: 테스트 전체 `OK`, 컴파일 에러 없음.

- [ ] **Step 2: 이동 누락 검사**

기존 `printer_server.py`의 모든 공개 동작이 새 구조에 존재하는지 확인:

```bash
grep -c "def " app/*.py printer_server.py
git -C . log --oneline
```

원본 대비 누락된 함수/엔드포인트가 없는지 육안 확인 (엔드포인트 6개: /printers, /print-image, /print-jobs/{job_id}, /health, /close-kiosk, /shutdown).

- [ ] **Step 3: 사용자에게 Windows 스모크 테스트 요청**

WSL에서는 GUI/인쇄를 실행할 수 없으므로, `docs/smoke-test.md` 체크리스트를 사용자에게 안내하고 Windows 실기 검증을 요청한다. **스모크 테스트 통과 전에는 릴리스 빌드(`build_release.py`)를 진행하지 않는다.**

---

## 자체 리뷰 결과 (계획 작성 시 수행)

- 스펙 커버리지: 모듈 분리(T2–T11), 인쇄 큐+API(T5, T8), GUI 반응성+자동갱신(T10), 수명주기(T9, T10), 로깅(T9, T10), 접속 범위(T10), Config(T4), 검증 전략(T3–T5 unittest + T12 스모크 문서), 버전/CHANGELOG(T12) — 전 항목 태스크 존재
- 스펙 대비 조정 2건: (a) pytest → stdlib unittest (WSL에 pip 없음, 목표 동일), (b) 작업 큐를 printing.py가 아닌 별도 jobs.py로 분리 (win32 없이 테스트 가능해야 한다는 스펙 요구 충족을 위함)
- 타입 일관성: `PrintJobQueue.submit(path, printer, filename)` / `get_job` / `start`, `kiosk.open_kiosk`/`close_kiosk`, `Config.get/set/port`, `UvicornServer.started/is_alive/stop` — 정의(T5–T9)와 사용(T8, T10, T11) 시그니처 일치 확인
```
