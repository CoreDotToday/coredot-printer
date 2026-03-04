# 코어닷투데이 프린터 API 서버 - 도움말

## 문제 해결

| 증상 | 해결 방법 |
|------|----------|
| 프린터 목록이 비어있음 | Windows에서 프린터 설치 확인 후 새로고침 클릭 |
| 연결 거부됨 | 포트 번호 확인, 방화벽 설정 확인 |
| 인쇄 안됨 | 프린터 전원/용지/잉크 확인, 오프라인 상태 해제 |
| 서버가 이미 실행 중 | 기존 프린터 서버 종료 후 재실행 |

## API 사용법

### 프린터 목록 조회
```
GET http://localhost:8000/printers
```

### 이미지 인쇄
```
POST http://localhost:8000/print-image
Content-Type: multipart/form-data

- file: 이미지 파일 (필수)
- printer: 프린터 이름 (선택)
```

### 예시 (cURL)
```bash
curl -X POST -F "file=@image.png" http://localhost:8000/print-image
```

## 문의

- GitHub Issues: https://github.com/CoreDotToday/coredot-printer/issues
