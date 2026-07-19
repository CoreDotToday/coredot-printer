# 모의 프린터 서버 (맥 개발용) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 맥/리눅스에서 실서버와 동일한 API를 제공하는 zero-dependency 단일 파일 모의 프린터 서버를 공개 repo로 배포한다.

**Architecture:** `dev/printer_mock.py` 단일 파일, 표준 라이브러리만 사용 (`http.server.ThreadingHTTPServer` + 자체 multipart 파서 + `threading.Timer` 상태 전이). 실서버 v2.4.0 응답 형식과 필드 단위 일치. 스펙: `docs/superpowers/specs/2026-07-19-mac-mock-server-design.md`.

**Tech Stack:** Python 3.9+ stdlib only. 검증은 WSL에서 curl 실테스트 (모의 서버는 크로스플랫폼이므로 WSL 실행 = 맥 동작과 동일).

**참고:** 이 파일은 외부(공개) repo에 들어가므로 커밋은 외부 repo에서, 트레일러 포함.

---

### Task 1: dev/printer_mock.py 작성

**Files:**
- Create: `dev/printer_mock.py`

- [ ] **Step 1: 파일 작성 (전체 코드)**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""개발용 모의(mock) 프린터 서버 — 맥/리눅스/윈도우, 표준 라이브러리만 사용.

키오스크 웹앱 개발 시 Windows 전용 실서버 없이 동일한 API를 사용할 수 있다.
실서버: 코어닷투데이 프린터 API 서버 (엔드포인트 계약 v2.4.0 기준)

⚠️ 실서버 API(엔드포인트·응답 형식)가 바뀌면 이 파일도 함께 갱신할 것.

사용법:
    python3 printer_mock.py                  # http://localhost:8000
    python3 printer_mock.py --port 9000      # 포트 변경
    python3 printer_mock.py --delay 5        # 인쇄 완료까지 5초
    python3 printer_mock.py --no-preview     # 이미지 미리보기 자동 열기 끔
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRINTER_OK = "Mock Printer"
PRINTER_OFFLINE = "Mock Printer Offline"
PRINTERS = [
    {"name": PRINTER_OK, "is_default": True},
    {"name": PRINTER_OFFLINE, "is_default": False},
]

QUEUED, PRINTING, DONE, ERROR = "queued", "printing", "done", "error"

PRINT_DIR = "mock-prints"

_jobs = {}
_jobs_lock = threading.Lock()

# 실행 옵션 (main에서 설정)
OPTIONS = argparse.Namespace(delay=2.0, preview=True)


def detect_image_ext(data):
    """이미지 매직 바이트 검사. 지원 형식이면 확장자, 아니면 None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"\xff\xd8":
        return ".jpg"
    if data[:4] == b"GIF8":
        return ".gif"
    if data[:2] == b"BM":
        return ".bmp"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def open_preview(path):
    """저장된 이미지를 OS 기본 뷰어로 연다 (실패해도 무시)."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path])
        elif os.name == "nt":
            os.startfile(path)  # noqa: 윈도우 전용
    except Exception as e:
        print(f"[경고] 미리보기 열기 실패: {e}")


def parse_multipart(body, content_type):
    """multipart/form-data 본문을 {name: (filename, data)}로 파싱.

    cgi 모듈이 Python 3.13에서 제거되어 직접 구현한다.
    """
    m = re.search(r'boundary="?([^";,]+)"?', content_type)
    if not m:
        return {}
    boundary = m.group(1).encode()
    parts = body.split(b"--" + boundary)
    fields = {}
    for part in parts[1:-1]:          # 첫 조각(프리앰블)과 마지막 조각(--) 제외
        part = part.lstrip(b"\r\n")
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, data = part.split(b"\r\n\r\n", 1)
        data = data.rstrip(b"\r\n")   # 파트 끝의 CRLF 제거
        disposition = ""
        for line in raw_headers.decode("utf-8", errors="replace").split("\r\n"):
            if line.lower().startswith("content-disposition"):
                disposition = line
        name_m = re.search(r'name="([^"]*)"', disposition)
        file_m = re.search(r'filename="([^"]*)"', disposition)
        if name_m:
            fields[name_m.group(1)] = (file_m.group(1) if file_m else None, data)
    return fields


def submit_job(filename, printer, image_data, ext):
    """작업 등록 + 이미지 저장 + 상태 전이 예약. job_id 반환."""
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id, "status": QUEUED, "file": filename,
            "printer": printer, "error": None,
        }

    os.makedirs(PRINT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved = os.path.join(PRINT_DIR, f"{stamp}-{job_id[:8]}{ext}")
    with open(saved, "wb") as f:
        f.write(image_data)
    print(f"[인쇄] job {job_id[:8]} ({printer}) → {saved}")

    def set_status(status, error=None):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["status"] = status
                job["error"] = error
        print(f"[상태] job {job_id[:8]} → {status}" + (f" ({error})" if error else ""))

    delay = OPTIONS.delay
    threading.Timer(delay * 0.3, set_status, [PRINTING]).start()
    if printer == PRINTER_OFFLINE:
        threading.Timer(delay, set_status, [ERROR, "프린터가 오프라인 상태입니다."]).start()
    else:
        threading.Timer(delay, set_status, [DONE]).start()
        if OPTIONS.preview:
            open_preview(saved)
    return job_id


class Handler(BaseHTTPRequestHandler):
    server_version = "MockPrinterServer/1.0"

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/printers":
            self._send_json(200, {
                "printers": PRINTERS,
                "default": PRINTER_OK,
                "count": len(PRINTERS),
            })
        elif self.path.startswith("/print-jobs/"):
            job_id = self.path[len("/print-jobs/"):]
            with _jobs_lock:
                job = _jobs.get(job_id)
                job = dict(job) if job else None
            if job is None:
                self._send_json(404, {"detail": "작업을 찾을 수 없습니다."})
            else:
                self._send_json(200, job)
        else:
            self._send_json(404, {"detail": "Not Found"})

    def do_POST(self):
        if self.path == "/close-kiosk":
            self._send_json(200, {"status": "no_process"})
        elif self.path == "/shutdown":
            print("[모의] 시스템 종료 요청 (실제 동작 없음)")
            self._send_json(200, {"status": "ok", "message": "5초 후 시스템이 종료됩니다."})
        elif self.path == "/print-image":
            self._handle_print_image()
        else:
            self._send_json(404, {"detail": "Not Found"})

    def _handle_print_image(self):
        length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json(400, {"detail": "multipart/form-data 요청이 필요합니다."})
            return
        fields = parse_multipart(self.rfile.read(length), content_type)

        if "file" not in fields or fields["file"][0] is None:
            self._send_json(400, {"detail": "file 필드가 필요합니다."})
            return
        filename, image_data = fields["file"]
        printer_field = fields.get("printer")
        printer = printer_field[1].decode("utf-8", errors="replace").strip() if printer_field else ""

        target_printer = printer or PRINTER_OK
        if target_printer not in [p["name"] for p in PRINTERS]:
            self._send_json(400, {"detail": f"프린터를 찾을 수 없습니다: {target_printer}"})
            return

        ext = detect_image_ext(image_data)
        if ext is None:
            self._send_json(400, {"detail": "유효한 이미지 파일이 아닙니다."})
            return

        job_id = submit_job(filename, target_printer, image_data, ext)
        self._send_json(200, {
            "status": "queued", "file": filename,
            "printer": target_printer, "job_id": job_id,
        })

    def log_message(self, fmt, *args):
        print(f"[요청] {self.command} {self.path}")


def main():
    parser = argparse.ArgumentParser(description="개발용 모의 프린터 서버")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--delay", type=float, default=2.0, help="인쇄 완료까지 걸리는 초 (기본 2.0)")
    parser.add_argument("--no-preview", action="store_true", help="이미지 미리보기 자동 열기 끔")
    args = parser.parse_args()
    OPTIONS.delay = args.delay
    OPTIONS.preview = not args.no_preview

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print("=" * 56)
    print("  모의 프린터 서버 (개발용) — 실제 인쇄는 하지 않습니다")
    print("=" * 56)
    print(f"주소:        http://localhost:{args.port}")
    print(f"프린터:      {PRINTER_OK} (기본) / {PRINTER_OFFLINE} (항상 실패)")
    print(f"인쇄 지연:   {args.delay}초  ·  미리보기: {'켬' if OPTIONS.preview else '끔'}")
    print(f"저장 폴더:   ./{PRINT_DIR}/")
    print("엔드포인트:  GET /printers · POST /print-image · GET /print-jobs/{id}")
    print("             GET /health · POST /close-kiosk · POST /shutdown")
    print("종료: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 문법 검증**

Run: `python3 -m py_compile dev/printer_mock.py`
Expected: 출력 없음 (성공)

### Task 2: curl 실테스트 (WSL)

- [ ] **Step 1: 서버 기동 + 테스트 이미지 준비**

```bash
cd /mnt/c/Users/kyunghoon/projects/coredot-printer
python3 dev/printer_mock.py --port 8123 --delay 1 --no-preview &   # 백그라운드
sleep 1
# 1x1 PNG 생성 (PIL 불필요)
python3 -c "import base64; open('/tmp/t.png','wb').write(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='))"
echo "텍스트" > /tmp/not_image.txt
```

- [ ] **Step 2: 엔드포인트 검증 (각 항목 기대값 확인)**

```bash
curl -s localhost:8123/health                       # {"status": "ok"}
curl -s localhost:8123/printers                     # printers 2개, default "Mock Printer", count 2
JOB=$(curl -s -F file=@/tmp/t.png localhost:8123/print-image | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
curl -s localhost:8123/print-jobs/$JOB              # queued 또는 printing
sleep 1.5
curl -s localhost:8123/print-jobs/$JOB              # "status": "done"
JOB2=$(curl -s -F file=@/tmp/t.png -F "printer=Mock Printer Offline" localhost:8123/print-image | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
sleep 1.5
curl -s localhost:8123/print-jobs/$JOB2             # "status": "error", 오프라인 메시지
curl -s -w '%{http_code}' -F file=@/tmp/t.png -F "printer=없는프린터" localhost:8123/print-image   # 400 + detail
curl -s -w '%{http_code}' -F file=@/tmp/not_image.txt localhost:8123/print-image                   # 400 유효한 이미지 아님
curl -s -w '%{http_code}' localhost:8123/print-jobs/nope    # 404
curl -si -X OPTIONS localhost:8123/print-image | head -5    # 204 + Access-Control-Allow-Origin: *
curl -s -X POST localhost:8123/close-kiosk                  # {"status": "no_process"}
curl -s -X POST localhost:8123/shutdown                     # ok + 5초 메시지 (실제 종료 없음)
ls mock-prints/                                             # 저장된 png 2개
```

- [ ] **Step 3: 서버 종료 + 테스트 산출물 정리**

```bash
kill %1
rm -rf mock-prints /tmp/t.png /tmp/not_image.txt
```

### Task 3: 문서 갱신

**Files:**
- Modify: `README.md` (API 섹션 뒤에 개발용 모의 서버 안내 추가)
- Modify: `CLAUDE.md` (drift 방지 규칙)
- Modify: `.gitignore` (mock-prints/ 제외)

- [ ] **Step 1: README.md에 섹션 추가** (## 요구사항 앞)

```markdown
## 개발용 모의 서버 (맥/리눅스)

실서버는 Windows 전용입니다. 맥·리눅스에서 키오스크 앱을 개발할 때는 모의 서버를 사용하세요 (Python 3.9+만 필요):

```bash
curl -O https://raw.githubusercontent.com/CoreDotToday/coredot-printer/main/dev/printer_mock.py
python3 printer_mock.py
```

동일한 API를 제공하며, 인쇄된 이미지는 `./mock-prints/`에 저장되고 자동으로 미리보기가 열립니다.
`Mock Printer Offline` 프린터로 인쇄하면 실패(job `error`) 케이스를 재현할 수 있습니다.
옵션: `--port`, `--delay <초>`, `--no-preview`
```

- [ ] **Step 2: CLAUDE.md의 Key Implementation Details에 항목 추가**

```markdown
- **Mock server contract**: `dev/printer_mock.py` mirrors the real API for mac/linux kiosk developers — update it whenever endpoints or response shapes change
```

- [ ] **Step 3: `.gitignore`에 `mock-prints/` 추가**

### Task 4: 커밋·푸시

- [ ] **Step 1: 외부 repo 커밋 (트레일러 포함) 후 푸시**

```bash
git add dev/printer_mock.py README.md CLAUDE.md .gitignore
git commit -m "feat: 맥/리눅스 개발용 모의 프린터 서버 추가 (zero-dependency)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

## 자체 리뷰

- 스펙 커버리지: 배포(T1+T3), API 계약 전체(T1, 응답 형식은 스펙 표와 동일 문자열), 편의 기능 3종(delay/preview/저장 — T1), CORS+OPTIONS(T1), drift 규칙(T3), 검증(T2) — 전 항목 반영
- 타입 일관성: `fields[name] = (filename, data)` 튜플 구조를 `_handle_print_image`가 동일하게 언팩; `OPTIONS` 네임스페이스 필드(delay/preview) 일치
- 플레이스홀더 없음
