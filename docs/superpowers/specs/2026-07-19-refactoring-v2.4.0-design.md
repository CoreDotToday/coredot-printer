# 프린터 서버 v2.4.0 리팩토링 설계

- **날짜**: 2026-07-19
- **대상**: `src/printer_server.py` (v2.3.0, 1,466줄 단일 파일)
- **목표**: 사용성·성능 개선 + 모듈 분리. 기존 API 클라이언트 및 배포 현장과의 호환성 유지.

## 배경 (분석 요약)

현재 코드는 단일 파일에 5개 관심사(설정, 자동실행, 키오스크, API 서버, GUI)가 섞여 있으며, 다음 문제가 확인되었다.

**성능·안정성:**
1. `load_printers()`가 GUI 스레드에서 프린터별 상태를 동기 조회 — 오프라인 네트워크 프린터가 있으면 앱 시작·새로고침 시 창 전체가 수 초간 멈춤
2. `/print-image`가 무조건 `"queued"`를 반환 — 잘못된 프린터명, 손상 이미지, 오프라인 모두 조용히 실패하고 클라이언트가 알 수 없음. 인쇄 태스크 예외 시 임시 파일 정리 태스크가 실행되지 않아 임시 파일 누적
3. `stop_server()`가 스레드 종료를 기다리지 않음 — 재시작 시 포트 미해제 경쟁. 시작 성공 판정이 1초 타이머 추측 기반. `on_closing()`의 `time.sleep(0.5)`가 GUI 블로킹
4. GUI 로그 텍스트박스 무한 증가 — 수 주 연속 가동하는 키오스크에서 메모리 증가
5. `print_without_margins()` 예외 시 DC 핸들 누수 (`AbortDoc`/`DeleteDC` 정리 없음)
6. `except: pass` 약 15곳 — 현장 장애 진단 불가
7. 전역 가변 상태(`_selected_printer`, `_kiosk_process`)를 GUI/서버 스레드가 락 없이 공유. `load_config()→수정→save_config()` 패턴이 7곳에 중복

**보안:**
- `0.0.0.0` 바인딩 + CORS 전면 개방 + `POST /shutdown`(Windows 종료) 무인증 — 같은 네트워크의 누구나 키오스크 PC를 끌 수 있음

## 설계

### 1. 모듈 구조

`printer_server.py`는 진입점으로 유지(빌드 스크립트 호환), 본체를 `app/` 패키지로 분리한다. Nuitka는 import를 따라가므로 빌드 스크립트 변경 불필요.

```
src/
  printer_server.py     # 진입점 (~30줄): 콘솔 숨김, stderr 리다이렉트, 중복 실행 감지, GUI 기동
  app/
    __init__.py         # VERSION, APP_NAME, 포트 상수 등
    changelog.py        # CHANGELOG 데이터
    config.py           # Config 클래스 — 로드/저장 일원화, threading.Lock으로 스레드 안전
    autostart.py        # 레지스트리 자동 실행 (winreg)
    kiosk.py            # Chrome 탐색/키오스크 실행/종료
    printing.py         # win32 프린터 열거·상태 조회·인쇄 + 인쇄 작업 큐(PrintJobQueue)
    api.py              # FastAPI 앱·엔드포인트
    server.py           # UvicornServer
    gui.py              # PrinterAPILauncher
```

win32 의존은 `printing.py`·`autostart.py`에 격리 — 나머지 모듈은 비Windows 환경에서도 import·테스트 가능해야 한다.

### 2. 인쇄 작업 큐 및 API 변경

- `BackgroundTasks` 대신 **전용 워커 스레드 1개**가 작업 큐에서 순차 인쇄 (프린터 특성상 직렬 처리)
- **사전 검증 후 큐잉**: 요청 시점에 (a) 대상 프린터가 설치 목록에 존재하는지, (b) PIL로 이미지가 열리는지 검증. 실패 시 즉시 HTTP 4xx 반환
- 응답에 `job_id`(uuid) 추가. 기존 필드 `status/file/printer`는 유지 → 기존 클라이언트 호환
- 신규 엔드포인트 `GET /print-jobs/{job_id}` — 상태: `queued` / `printing` / `done` / `error`(+ 오류 메시지). 완료된 작업은 최근 N건(기본 100)만 메모리에 유지
- 임시 파일은 워커에서 `finally`로 삭제 보장
- 인쇄 렌더링 동작(이미지를 인쇄 영역에 맞춰 늘림)은 **변경하지 않음** — 현장 회귀 방지

### 3. GUI 반응성·상태 자동 갱신

- 프린터 목록·상태 조회를 백그라운드 스레드로 이동, `root.after()`로 UI 반영. 목록(이름)은 즉시 표시하고 상태 라벨은 조회 완료 시 갱신
- GUI가 떠 있는 동안 **30초 주기**로 상태 자동 갱신 (수동 새로고침 버튼 유지)
- 갱신 중 재진입 방지 (조회 스레드 1개만 유지)

### 4. 서버 수명주기 신뢰성

- 시작 판정: `uvicorn.Server.started` 속성 폴링 (`root.after` 반복) — 성공/실패를 정확히 감지
- 중지: `should_exit` 설정 후 스레드 `join`(타임아웃) — 재시작은 이전 스레드 종료 확인 후 수행
- `on_closing()`: `time.sleep` 제거, 동일한 join-후-종료 방식 적용

### 5. 로깅

- GUI 로그는 **최근 1,000줄** 링 버퍼로 유지 (초과분 앞에서 삭제)
- `/health` 접근 로그 필터링 (uvicorn access log filter)
- `except: pass` 전면 제거 → 최소 `logging.warning`으로 기록 (stderr→error.log 및 GUI 로그로 전달). 의도적 무시가 정당한 곳(예: 아이콘 로드 실패)도 디버그 로그는 남김
- 인쇄 함수는 `try/finally`로 DC 정리, 실패 시 `AbortDoc` 호출

### 6. 접속 범위 설정 (보안)

- GUI 체크박스 **"외부 접속 허용 (같은 네트워크)"** 추가
  - 켜짐(기본값, 기존 동작): `0.0.0.0` 바인딩 — 같은 공유기 내 다른 기기에서 호출 가능
  - 꺼짐: `127.0.0.1` 바인딩 — 같은 PC의 키오스크 웹앱만 호출 가능
- `config.json`에 `allow_external`(bool, 기본 `true`) 저장. 서버 재시작 시 적용, 실행 중 변경 시 재시작 안내 표시
- 기본값이 기존 동작이므로 배포 현장 무영향

### 7. Config 클래스

- 단일 `Config` 인스턴스가 `config.json` 로드/저장을 전담, `threading.Lock`으로 동시 접근 보호
- `config.get(key)` / `config.set(key, value)`(즉시 저장) 인터페이스
- 기존 키(`port`, `printer`, `auto_start`, `saved_urls`, `kiosk_url`, `kiosk_auto_open`, `kiosk_zoom`) 그대로 유지 + `allow_external` 추가 — 기존 config.json 파일과 호환

### 8. 검증 전략

- **pytest 단위 테스트 신설** (`src/tests/`): `config.py`(로드/저장/포트 검증/손상 파일), 인쇄 작업 상태 머신, changelog 태그 파싱 등 win32 비의존 로직 — WSL/Linux에서 실행 가능하도록 win32 import를 지연/격리
- **Windows 수동 스모크 체크리스트** (`docs/smoke-test.md`): 서버 시작/중지/재시작, 인쇄 성공/실패 케이스, job 상태 조회, 키오스크 열기/닫기, 자동 실행 등록/해제, 포트 변경, 외부 접속 허용/차단, 중복 실행 감지
- 버전 `2.4.0`, `CHANGELOG`(코드 상수)와 `CHANGELOG.md` 갱신

## 변경하지 않는 것 (스코프 제외)

- 인쇄 렌더링 방식 (종횡비 늘림 유지)
- 설정 '저장' 버튼 3개 (자동 저장 미도입)
- 트레이 최소화, 창 크기 조절
- API 토큰 인증 (접속 범위 설정으로 갈음)
- 창 레이아웃·테마 등 시각 디자인
