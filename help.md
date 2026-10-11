# 코어닷투데이 프린터 API 서버 - 도움말

## 문제 해결

| 증상 | 해결 방법 |
|------|----------|
| 프린터 목록이 비어있음 | Windows에서 프린터 설치 확인 후 **새로고침** 클릭 |
| 선택한 프린터가 **미연결**로 표시됨 | 프린터 전원·USB·네트워크 확인. 연결되면 자동으로 다시 사용됩니다 (선택을 바꿀 필요 없음) |
| 연결 거부됨 | 포트 번호 확인, 방화벽 설정 확인. 다른 기기에서 접속하려면 **외부 접속 허용** 체크 후 재시작 |
| 인쇄 안됨 | 프린터 전원/용지/잉크 확인, "오프라인으로 사용" 해제. `GET /print-jobs/{job_id}`의 `error` 메시지 확인 |
| 서버가 이미 실행 중 | 기존 프린터 서버 종료 후 재실행 (작업 표시줄·트레이 확인) |
| `/shutdown`, `/close-kiosk`가 403 | 기본값은 같은 PC 요청만 허용. 다른 기기에서 쓰려면 **원격 제어 허용** 체크 |
| 사진이 옆으로 인쇄됨 | v2.8.0부터 휴대폰 사진의 회전 정보(EXIF)를 자동 반영합니다. 최신 버전으로 업데이트 |
| 자동 실행이 안 됨 | exe를 옮기거나 이름을 바꿨다면 앱을 한 번 실행하면 경로가 자동 갱신됩니다 |
| 더블클릭해도 아무것도 안 뜸 | 아래 **"실행해도 아무것도 안 뜰 때"** 절 참고 |
| 원인을 모르겠음 | exe 옆 `startup.log`(기동 단계), `server.log`(요청·인쇄 기록), `error.log`·`error.log.1`(오류)을 고객지원에 전달 |

## 실행해도 아무것도 안 뜰 때

v2.9.0부터 더블클릭 직후 "시작하는 중" 창이 먼저 뜹니다. 첫 실행은 파일을 준비하느라 수십 초 걸릴 수 있고, 두 번째부터는 바로 뜹니다. 그래도 안 뜨면 순서대로 확인하세요.

1. **`startup.log` 확인** — exe 옆, 없으면 `%LOCALAPPDATA%\CoreDotPrinter\` (탐색기 주소창에 그대로 입력).
   - 파일 자체가 없음 → 프로그램이 시작조차 못 한 것. 백신 보호 기록, SmartScreen, 회사 PC의 AppLocker 정책을 확인하세요.
   - 마지막 줄이 `start` → 다음 단계 전에 멈춤. 같은 폴더의 `error.log`를 보세요.
   - 마지막 줄이 `FATAL …` → 오류 내용이 그 줄과 `error.log`에 있습니다.
   - `gui created`·`mainloop`까지 있음 → 창은 만들어졌습니다. 다른 모니터·작업 표시줄 뒤에 있는지 확인하세요.
2. **cmd 창에서 실행** — 시작 메뉴에서 `cmd`를 열고 exe 파일을 창으로 끌어다 놓은 뒤 Enter. 오류가 그 창에 그대로 표시됩니다.
3. **준비 폴더 초기화** — `%LOCALAPPDATA%\CoreDotPrinter\<버전>` 폴더를 지우고 다시 실행하면 파일을 새로 풉니다.
4. **설치 위치** — `C:\CoreDotPrinter\` 같은 단순한 폴더에 두세요. Program Files·네트워크 드라이브·OneDrive 동기화 폴더는 피합니다.

위 내용과 함께 `startup.log`·`error.log`를 고객지원에 보내주시면 바로 원인을 찾을 수 있습니다.

## 설정 (GUI [기본] 탭)

| 항목 | 설명 | 기본값 |
|------|------|--------|
| 포트 | API 포트 (1024~65535), 재시작 후 적용 | 8000 |
| 선택된 프린터 | API 요청에 `printer`가 없을 때 사용 | Windows 기본 프린터 |
| Windows 시작 시 자동 실행 | 로그인 시 앱·서버 자동 시작 | 끔 |
| 외부 접속 허용 | 같은 네트워크 기기에서 접속 허용 (끄면 같은 PC만) | 켬 |
| 원격 제어 허용 | 다른 기기에서 `/shutdown`·`/close-kiosk` 호출 허용 | 끔 |
| 키오스크 URL / 자동 열기 / 확대율 | 서버 시작 시 Chrome 풀스크린으로 열 페이지 | - |

설정은 exe 옆 `config.json`에 저장됩니다. 템플릿·배경·폰트는 `data/` 폴더에서 관리합니다.

## API 사용법

기본 주소: `http://localhost:8000` (외부 접속 허용 시 GUI에 표시되는 내부 IP 사용)

### 상태 확인
```
GET /health
→ {"status":"ok","app":"coredot-printer","version":"2.8.0"}
```

### 프린터 목록
```
GET /printers
→ {"printers":[{"name":"...","is_default":true}],"default":"...","count":1}
```

### 이미지 인쇄 (여백 없음)
```
POST /print-image
Content-Type: multipart/form-data

- file: 이미지 파일 (필수, 최대 50MB)
- printer: 프린터 이름 (선택)

→ {"status":"queued","file":"image.png","printer":"...","job_id":"..."}
```
오류: 400(프린터 없음·이미지 아님), 413(너무 큼), 503(대기열 20건 초과 — 잠시 후 재시도)

### 인쇄 작업 상태
```
GET /print-jobs/{job_id}
→ {"id":"...","status":"queued|printing|done|error","file":"...","printer":"...","error":null}
```

### 템플릿 목록
```
GET /templates
→ {"templates":[{"id":"감사장","name":"감사장","size":"A4","dpi":300,"orientation":"portrait",
                 "params":[{"param":"photo","type":"image","required":false},
                           {"param":"name","type":"text","required":true}]}],"count":1}
```
`id`는 `data/templates/` 안의 파일명이며, 아래 두 API의 `template` 값으로 씁니다.

### 템플릿 조판 인쇄
```
POST /print-template
Content-Type: multipart/form-data

- template: 템플릿 id (필수)
- printer: 프린터 이름 (선택)
- 요소 파라미터: text/qr은 문자열, image는 파일 업로드·http(s) URL·data URI (최대 20MB)

→ {"status":"queued","template":"감사장","printer":"...","job_id":"..."}
```

### 템플릿 미리보기 (PNG)
```
GET /preview-template?template=감사장&name=홍길동&dpi=150
```
`dpi`는 72~300. 이미지 파라미터는 URL 또는 data URI로 전달합니다.

### 키오스크·시스템 제어 (기본: 같은 PC에서만)
```
POST /close-kiosk   → {"status":"closed|no_process|error"}
POST /shutdown      → {"status":"ok","message":"5초 후 시스템이 종료됩니다."}
```
다른 기기에서 호출하면 403. GUI의 **원격 제어 허용**을 켜면 같은 네트워크에서도 가능합니다.

### 예시 (cURL)
```bash
curl -X POST -F "file=@image.png" http://localhost:8000/print-image
curl -X POST -F "template=감사장" -F "name=홍길동" -F "photo=@photo.jpg" http://localhost:8000/print-template
curl "http://localhost:8000/print-jobs/<job_id>"
```

전체 문서: `http://localhost:8000/docs` (Swagger UI)

## 개발용 모의 서버 (맥/리눅스)

실서버는 Windows 전용입니다. 다른 OS에서 키오스크 앱을 개발할 때는 `dev/printer_mock.py`를 사용하세요 (Python 3.9+, 표준 라이브러리만).

## 문의

- GitHub Issues: https://github.com/CoreDotToday/coredot-printer/issues
