# 템플릿 조판 인쇄 플랫폼 설계 (v2.5.0)

- **날짜**: 2026-07-19
- **배경**: `kogongjang-print`(감사장 인쇄 시스템, Flask+fpdf2+SumatraPDF)와 프린터서버는
  인프라(GUI/키오스크/자동실행/빌드)가 중복된 형제 프로젝트다. 프린터서버를 인쇄 플랫폼으로
  통합하고, 감사장 같은 도메인 조판을 **JSON 템플릿**으로 일반화해 다양한 키오스크가
  재사용할 수 있게 한다.
- **승인된 방향**: 통합 exe 하나, kogongjang API/포트(5000) 호환 불필요, 조판 미리보기 제공,
  요소는 텍스트·이미지·**QR코드** 3종으로 시작.

## 1. 템플릿 스키마 (`data/templates/*.json`)

모든 키오스크가 사용할 계약. 파일명(확장자 제외)이 템플릿 식별자.

```json
{
  "name": "감사장",
  "size": "A4",
  "orientation": "portrait",
  "dpi": 300,
  "background": "background_kogongjang.png",
  "elements": [
    {"type": "image", "param": "photo", "box_mm": [24.3, 65.6, 49.0, 53.3],
     "fit": "cover", "border": {"width_mm": 1.0, "color": "#000000"}, "required": false},
    {"type": "text", "param": "name", "box_mm": [7.1, 105.8, 176.4, 123.5],
     "font": "nanum.ttf", "size_pt": 24, "color": "#000000",
     "align": "center", "valign": "middle", "required": true},
    {"type": "qr", "param": "qr_data", "box_mm": [170, 260, 25, 25],
     "color": "#000000", "required": false}
  ]
}
```

- **좌표**: `box_mm = [x, y, w, h]` — mm 단위, 좌상단 원점. `size`: `"A4"`(210×297) 지원,
  스키마상 `[w_mm, h_mm]` 배열도 허용(비표준 용지 확장). `orientation`: `portrait`/`landscape`
- **공통 필드**: `type`(text/image/qr), `param`(API 파라미터명, 템플릿 내 유일),
  `box_mm`, `required`(기본 true; false인 요소는 파라미터 생략 시 그리지 않음)
- **text**: `font`(data/fonts/ 우선, 번들 폴백), `size_pt`, `color`(#RRGGBB),
  `align`(left/center/right, 기본 center), `valign`(top/middle/bottom, 기본 middle).
  텍스트가 박스 폭을 넘으면 자동 줄바꿈, 박스를 벗어나면 축소 없이 잘리지 않게
  폰트 크기를 단계적으로 줄인다(최소 8pt)
- **image**: `fit`(cover/contain, 기본 cover), `border`(선택: width_mm, color)
- **qr**: `color`(전경색, 기본 #000000; 배경 투명), 오류정정 레벨 M 고정(YAGNI)
- `background`: data/backgrounds/ 우선, 번들 폴백. 생략 가능(흰 배경)
- 알 수 없는 `type`/필수 필드 누락은 템플릿 로드 시 검증 오류

## 2. 조판 엔진 (`app/compose.py`)

- 순수 PIL + `qrcode` 라이브러리(순수 Python, PIL 의존 — 신규 의존성은 이것 하나)
- `render(template: dict, params: dict[str, str|bytes]) -> PIL.Image` —
  mm→px 변환(dpi 기준), 배경 → 요소 순서대로 그리기
- 이미지 파라미터 입력: bytes(업로드), `http(s)://` URL(urllib, 5초 타임아웃),
  `data:image/...;base64,` URI 모두 지원 (kogongjang 계약 계승)
- 필수 파라미터 누락 → `TemplateParamError`(API가 400으로 변환)
- 템플릿 로드/검증은 `load_template(name)` / `validate_template(dict)`로 분리 (단위 테스트 대상)

## 3. API 확장 (`app/api.py` — 기존 엔드포인트 전부 불변)

| 메서드 | 경로 | 동작 |
|---|---|---|
| `GET` | `/templates` | `{"templates": [{name, params: [{param, type, required}], size, dpi}], "count"}` — 키오스크가 동적 폼 구성 가능 |
| `POST` | `/print-template` | multipart/form-data: `template`(필수), `printer`(선택), 텍스트/QR 파라미터는 문자열 필드, 이미지 파라미터는 파일 필드 또는 URL/base64 문자열. 검증(템플릿 존재·필수 파라미터·프린터 존재) 후 조판 → PNG 임시 파일 → 기존 작업 큐 제출 → `{"status":"queued","template","printer","job_id"}` |
| `GET` | `/preview-template` | 쿼리스트링으로 `template` + 텍스트/QR 파라미터(이미지 파라미터는 URL/base64만) → 조판 결과를 `image/png`로 반환. 인쇄와 동일 렌더러 — 보이는 그대로 인쇄됨 |

- 오류 형식은 기존과 동일: 400/404 + `{"detail": "..."}`
- 조판은 blocking이므로 sync `def` 핸들러 (기존 관례)
- 미리보기 성능: 미리보기는 dpi를 150으로 낮춰 렌더(쿼리 `dpi`로 재정의 가능) — 화면용은 충분히 선명하고 응답 빠름

## 4. 데이터 폴더 (`data/` — exe 옆, kogongjang 구조 계승)

```
data/
  templates/   *.json (감사장 템플릿 기본 제공)
  backgrounds/ 사용자 배경 PNG
  fonts/       사용자 TTF/OTF
```
- 번들 자원: 기본 한글 폰트 1종(나눔스퀘어 — kogongjang이 쓰던 것), kogongjang 배경 PNG,
  변환된 감사장 템플릿 JSON — 최초 실행 시 data/에 없으면 번들에서 복사(사용자 수정 가능하게)
- `Config`는 그대로 (템플릿 관련 설정 키 추가 없음 — 템플릿이 자체 완결)

## 5. kogongjang 마이그레이션

- kogongjang `config.json`의 pt 좌표(name_x/y/width/height, 사진 박스 (69,186,208,337)pt)를
  mm로 변환(`pt × 25.4 / 72`)한 감사장 템플릿 JSON을 기본 제공
- kogongjang-print 저장소는 아카이브 (이 스펙 범위 밖, 사용자 판단)
- 포트는 8000 단일화. `/preview`(HTML)·`/test`(PDF)·`/quit` 등 kogongjang 전용 라우트는 계승하지 않음

## 6. 빌드·배포

- `requirements.txt`에 `qrcode` 추가, `build_release.py`에 `--include-package=qrcode` 및
  번들 자원 `--include-data-dir`/`--include-data-file` 추가
- 예상 크기 증가: 폰트+배경 2~5MB 수준 (26MB → 약 30MB 이내)
- 버전 2.5.0, CHANGELOG(코드·MD)·모의 서버(`dev/printer_mock.py`)에 신규 3개 엔드포인트 반영,
  README·smoke-test.md 갱신

## 7. 검증

- WSL unittest: 템플릿 검증, mm→px 변환, 파라미터 스키마 추출, 폰트 크기 축소 로직 등 순수 로직
- PIL 렌더링: WSL에 Pillow 설치 가능 여부를 구현 시 확인 — 가능하면 렌더 결과 크기/픽셀 검사 테스트,
  불가하면 Windows 스모크로 대체
- Windows 스모크: 감사장 템플릿 미리보기 = 실제 인쇄물 일치, kogongjang 대비 품질 확인

## 스코프 제외

- 템플릿 편집 GUI (JSON 직접 편집; 필요 시 후속)
- PDF 생성/미리보기 (PNG로 대체), SumatraPDF, kogongjang 라우트 호환
- QR 오류정정/버전 세부 옵션, 바코드(1D), 날짜 자동 삽입 등 추가 요소 타입 (스키마가 확장 가능하므로 후속에서 추가)
- kogongjang 저장소 아카이브 작업
