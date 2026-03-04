# 코어닷투데이 AI 키오스크 프린터 서버

로컬 프린터를 HTTP API로 제어하는 서버입니다.

## 다운로드

[Releases](https://github.com/CoreDotToday/coredot-printer/releases)에서 `프린터서버.exe` 다운로드

## 사용법

1. `프린터서버.exe` 실행
2. 프린터 선택
3. **시작** 클릭
4. `http://localhost:8000`에서 API 사용

## API

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /printers` | 프린터 목록 |
| `POST /print-image` | 이미지 인쇄 |
| `GET /docs` | API 문서 |

### 인쇄 예시

```bash
curl -X POST -F "file=@image.png" http://localhost:8000/print-image
```

## 요구사항

- Windows 10/11
- 프린터 드라이버 설치

---

**CoreDotToday**
