# 코어닷투데이 AI 키오스크 프린터 서버

**버전:** 1.0 (2025.12.02)

---

## 빠른 시작

1. `프린터서버.exe` 더블클릭
2. 프린터 선택
3. `▶ 서버 시작` 클릭
4. 키오스크에서 인쇄 사용 가능

---

## 서버 설정 정보

| 항목 | 기본값 | 설명 |
|------|--------|------|
| **포트 번호** | `8000` | 필요시 8050, 8080 등으로 변경 가능 |
| **서버 주소** | `http://localhost:8000` | 같은 PC에서 접속 시 |
| **외부 접속** | `http://[PC의 IP]:8000` | 다른 PC에서 접속 시 |

### 포트 번호 변경 방법
1. 서버 중지 상태에서 포트 번호 입력란에 원하는 포트 입력
2. 서버 시작

### 외부 접속 설정
다른 PC나 키오스크에서 접속하려면:
1. 이 PC의 IP 주소 확인 (예: `192.168.0.100`)
2. 방화벽에서 해당 포트 허용
3. 키오스크에서 `http://192.168.0.100:8000` 으로 접속

---

## API 엔드포인트

### 프린터 목록 조회
```
GET http://localhost:8000/printers
```

### 이미지 인쇄
```
POST http://localhost:8000/print-image
Content-Type: multipart/form-data

파라미터:
- file: 이미지 파일 (필수)
- printer: 프린터 이름 (선택, 생략 시 GUI에서 선택한 프린터 사용)
```

### API 문서 (Swagger)
```
http://localhost:8000/docs
```

---

## 키오스크 연동 예시

### JavaScript
```javascript
// 이미지 인쇄 요청
const formData = new FormData();
formData.append('file', imageBlob, 'print.png');

await fetch('http://localhost:8000/print-image', {
  method: 'POST',
  body: formData
});
```

### cURL
```bash
curl -X POST -F "file=@image.png" http://localhost:8000/print-image
```

---

## 문제 해결

| 증상 | 해결 방법 |
|------|----------|
| "프린터 서버가 이미 실행 중" | 기존 프린터 서버 종료 후 재실행 |
| 프린터 목록이 비어있음 | Windows에서 프린터 설치 확인 후 🔄 클릭 |
| 연결 거부됨 | 포트 번호 확인, 방화벽 설정 확인 |
| 인쇄 안됨 | 프린터 전원/용지/잉크 확인, 오프라인 상태 해제 |

---

## 폴더 구조

```
├── 프린터서버.exe   ← 실행 파일
├── _internal/       ← 필수 (삭제 금지!)
└── README.md
```

---

## 시스템 요구사항

- Windows 10 / 11
- 프린터 드라이버 설치됨
- Python 설치 불필요

---

**개발:** 코어닷투데이 (CoreDotToday)
