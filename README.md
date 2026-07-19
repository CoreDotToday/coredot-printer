# 코어닷투데이 AI 키오스크 프린터 서버

로컬 프린터를 HTTP API로 제어하는 서버입니다.

## 다운로드

[Releases](https://github.com/CoreDotToday/coredot-printer/releases)에서 `CoreDotPrinter-<버전>.exe` 다운로드

## 사용법

1. `CoreDotPrinter-<버전>.exe` 실행
2. 프린터 선택
3. **시작** 클릭
4. `http://localhost:8000`에서 API 사용

## API

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /printers` | 프린터 목록 |
| `POST /print-image` | 이미지 인쇄 |
| `GET /templates` | 조판 템플릿 목록 |
| `POST /print-template` | 템플릿 조판 인쇄 (감사장 등) |
| `GET /preview-template` | 조판 미리보기 (PNG) |
| `GET /docs` | API 문서 |

### 인쇄 예시

```bash
curl -X POST -F "file=@image.png" http://localhost:8000/print-image
```

## 개발용 모의 서버 (맥/리눅스)

실서버는 Windows 전용입니다. 맥·리눅스에서 키오스크 앱을 개발할 때는 모의 서버를 사용하세요 (Python 3.9+만 필요):

```bash
curl -O https://raw.githubusercontent.com/CoreDotToday/coredot-printer/main/dev/printer_mock.py
python3 printer_mock.py
```

동일한 API를 제공하며, 인쇄된 이미지는 `./mock-prints/`에 저장되고 자동으로 미리보기가 열립니다.
`Mock Printer Offline` 프린터로 인쇄하면 실패(job `error`) 케이스를 재현할 수 있습니다.
옵션: `--port`, `--delay <초>`, `--no-preview`

## 요구사항

- Windows 10/11
- 프린터 드라이버 설치

---

**CoreDotToday**
