# 맥/크로스플랫폼 개발용 모의 프린터 서버 설계

- **날짜**: 2026-07-19
- **배경**: 키오스크 웹앱 개발자들이 맥에서 Windows 전용 프린터 서버를 실행할 수 없어
  API 엔드포인트 연동 개발이 불가능함
- **결정**: 표준 라이브러리만 사용하는 zero-dependency 단일 파일 모의 서버를 공개 repo로 배포

## 배포

- 파일: `dev/printer_mock.py` (외부 공개 repo에 커밋)
- 실행: `python3 printer_mock.py` — pip/venv 불필요 (Python 3.9+ 가정)
- 안내: README에 다운로드·실행 방법 추가
  ```bash
  curl -O https://raw.githubusercontent.com/CoreDotToday/coredot-printer/main/dev/printer_mock.py
  python3 printer_mock.py
  ```
- 맥 바이너리 빌드는 하지 않는다 (맥에서만 빌드 가능해 유지 불가; 스크립트가 더 간편)

## API 계약 (실서버 v2.4.0과 응답 형식 동일)

| 엔드포인트 | 모의 동작 |
|---|---|
| `GET /printers` | `{"printers":[{name,is_default}...], "default", "count"}` — 가짜 2대: `Mock Printer`(기본·정상), `Mock Printer Offline`(항상 실패) |
| `POST /print-image` | multipart(`file` 필수, `printer` 선택). 미지정 시 기본 프린터. 없는 프린터명 → 400 `{"detail":"프린터를 찾을 수 없습니다: <이름>"}`. 이미지 아님(매직 바이트: PNG/JPEG/GIF/BMP/WebP) → 400 `{"detail":"유효한 이미지 파일이 아닙니다."}`. 성공 → `{"status":"queued","file","printer","job_id"}` |
| `GET /print-jobs/{id}` | `{"id","status","file","printer","error"}` — `queued→printing→done` 전이. Offline 프린터 작업은 `error` + `"프린터가 오프라인 상태입니다."`. 미존재 id → 404 `{"detail":"작업을 찾을 수 없습니다."}` |
| `GET /health` | `{"status":"ok"}` |
| `POST /close-kiosk` | `{"status":"no_process"}` |
| `POST /shutdown` | `{"status":"ok","message":"5초 후 시스템이 종료됩니다."}` — 실제 동작 없음, 콘솔에 `[모의]` 로그 |

- CORS: 모든 응답에 `Access-Control-Allow-Origin: *` 등 부여, `OPTIONS` preflight 204 처리
- 그 외 경로 → 404 `{"detail":"Not Found"}`

## 개발 편의 기능

- 받은 이미지를 `./mock-prints/<YYYYmmdd-HHMMSS>-<job_id 앞 8자>.<확장자>`로 저장,
  기본으로 OS 미리보기 자동 실행 (맥 `open` / 리눅스 `xdg-open` / 윈도우 `os.startfile`)
- CLI 옵션: `--port 8000`(기본), `--delay 2.0`(queued→done 소요 초), `--no-preview`
- 시작 시 콘솔에 주소·엔드포인트·옵션 요약 출력
- 인쇄 요청/상태 전이를 콘솔에 로그

## 구현 구조 (단일 파일 내)

- `http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler` — stdlib만 사용
- multipart 파싱: 자체 구현 (boundary 분리, `filename`/`name` 추출) — cgi 모듈은 3.13에서 제거되어 사용 금지
- job 저장소: dict + `threading.Lock`, 상태 전이는 `threading.Timer`(delay 후 printing→done/error)
- 이미지 매직 바이트 검사 함수 분리 (PNG `\x89PNG`, JPEG `\xff\xd8`, GIF `GIF8`, BMP `BM`, WebP `RIFF....WEBP`)

## 계약 drift 방지

- 파일 헤더 주석과 CLAUDE.md에 "실서버 API 변경 시 `dev/printer_mock.py`도 함께 갱신" 규칙 명시
- 자동 계약 테스트는 만들지 않는다 (실서버 api.py가 win32 의존이라 비Windows에서 import 불가; 엔드포인트 6개 규모에는 수동 동기화로 충분)

## 검증

- WSL에서 실행 후 curl로 전 엔드포인트 확인: 정상 인쇄 흐름(queued→done), Offline 프린터 error 전이,
  없는 프린터 400, 비이미지 400, 미존재 job 404, OPTIONS preflight, `--delay`/`--no-preview` 동작
- 미리보기 자동 열기는 맥에서 사용자(개발자)가 확인

## 스코프 제외

- 실제 인쇄(CUPS), 맥 바이너리 패키징, GUI, /docs(Swagger), 인증
