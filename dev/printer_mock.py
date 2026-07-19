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
