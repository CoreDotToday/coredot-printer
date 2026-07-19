# 템플릿 조판 인쇄 플랫폼 (v2.5.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** JSON 템플릿(텍스트·이미지·QR) 기반 조판 인쇄를 프린터서버에 통합해 kogongjang-print를 대체하고 범용 인쇄 플랫폼으로 확장한다.

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-19-template-printing-design.md` 기준. `app/template.py`(PIL 비의존: 로드·검증·스키마 — WSL 테스트 가능) + `app/compose.py`(PIL+qrcode 렌더러 — Windows 검증) + `app/api.py`에 3개 엔드포인트 추가. 번들 자원은 `src/assets/`, 사용자 자원은 exe 옆 `data/`.

**Tech Stack:** 기존 스택 + `qrcode`(순수 Python). 소스 커밋은 src 중첩 repo(한 줄, 트레일러 없음), 문서·모의서버는 외부 repo(트레일러 포함).

**환경 주의:** WSL에 Pillow/qrcode 없음 — compose.py는 `py_compile`만, template.py는 unittest. api.py의 신규 핸들러는 `async def` + `run_in_threadpool` (동적 form 파싱 때문에 기존 sync 관례와 다름 — 블로킹은 threadpool로 격리).

---

### Task 1: app/template.py — 템플릿 로드·검증·스키마 (TDD, WSL)

**Files:**
- Create: `src/app/template.py`
- Test: `src/tests/test_template.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `src/tests/test_template.py`:

```python
# -*- coding: utf-8 -*-
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from app import template as tpl


def minimal_template(**overrides):
    data = {
        "name": "테스트",
        "background": "bg.png",
        "elements": [
            {"type": "text", "param": "name", "box_mm": [10, 20, 100, 30],
             "font": "nanum.ttf", "size_pt": 24},
        ],
    }
    data.update(overrides)
    return data


class ValidateTemplateTest(unittest.TestCase):
    def test_minimal_valid_fills_defaults(self):
        t = tpl.validate_template(minimal_template())
        self.assertEqual(t["size"], "A4")
        self.assertEqual(t["dpi"], 300)
        self.assertEqual(t["orientation"], "portrait")
        el = t["elements"][0]
        self.assertEqual(el["align"], "center")
        self.assertEqual(el["valign"], "middle")
        self.assertEqual(el["color"], "#000000")
        self.assertTrue(el["required"])

    def test_unknown_element_type_rejected(self):
        data = minimal_template()
        data["elements"][0]["type"] = "barcode"
        with self.assertRaises(tpl.TemplateError):
            tpl.validate_template(data)

    def test_bad_box_rejected(self):
        for bad in ([1, 2, 3], "box", [0, 0, -5, 10]):
            data = minimal_template()
            data["elements"][0]["box_mm"] = bad
            with self.assertRaises(tpl.TemplateError):
                tpl.validate_template(data)

    def test_duplicate_param_rejected(self):
        data = minimal_template()
        data["elements"].append({"type": "qr", "param": "name", "box_mm": [1, 1, 20, 20]})
        with self.assertRaises(tpl.TemplateError):
            tpl.validate_template(data)

    def test_qr_and_image_defaults(self):
        data = minimal_template()
        data["elements"].append({"type": "qr", "param": "qr", "box_mm": [1, 1, 20, 20]})
        data["elements"].append({"type": "image", "param": "photo", "box_mm": [1, 1, 20, 20],
                                 "required": False})
        t = tpl.validate_template(data)
        self.assertEqual(t["elements"][1]["color"], "#000000")
        self.assertEqual(t["elements"][2]["fit"], "cover")
        self.assertIsNone(t["elements"][2]["border"])
        self.assertFalse(t["elements"][2]["required"])

    def test_custom_size_and_landscape(self):
        t = tpl.validate_template(minimal_template(size=[100, 150], orientation="landscape"))
        self.assertEqual(tpl.page_size_mm(t), (150.0, 100.0))

    def test_a4_portrait_size(self):
        t = tpl.validate_template(minimal_template())
        self.assertEqual(tpl.page_size_mm(t), (210.0, 297.0))


class MmToPxTest(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual(tpl.mm_to_px(25.4, 300), 300)
        self.assertEqual(tpl.mm_to_px(210, 300), 2480)


class ParamSchemaTest(unittest.TestCase):
    def test_schema(self):
        data = minimal_template()
        data["elements"].append({"type": "qr", "param": "qr", "box_mm": [1, 1, 20, 20],
                                 "required": False})
        schema = tpl.param_schema(tpl.validate_template(data))
        self.assertEqual(schema, [
            {"param": "name", "type": "text", "required": True},
            {"param": "qr", "type": "qr", "required": False},
        ])


class TemplateFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        self.bundled = os.path.join(self.tmp, "assets")
        for base in (self.data, self.bundled):
            os.makedirs(os.path.join(base, "templates"))
        self.p1 = mock.patch.object(tpl, "data_dir", lambda: self.data)
        self.p2 = mock.patch.object(tpl, "bundled_dir", lambda: self.bundled)
        self.p1.start(); self.p2.start()

    def tearDown(self):
        self.p1.stop(); self.p2.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, base, name, data):
        with open(os.path.join(base, "templates", name + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_load_template_prefers_data_dir(self):
        self._write(self.bundled, "감사장", minimal_template(dpi=150))
        self._write(self.data, "감사장", minimal_template(dpi=200))
        self.assertEqual(tpl.load_template("감사장")["dpi"], 200)

    def test_load_template_not_found(self):
        with self.assertRaises(tpl.TemplateNotFound):
            tpl.load_template("없음")

    def test_list_templates_skips_invalid(self):
        self._write(self.data, "정상", minimal_template())
        self._write(self.data, "고장", {"elements": "broken"})
        names = [t["name"] for t in tpl.list_templates()]
        self.assertEqual(names, ["테스트"])   # minimal_template의 name 필드

    def test_ensure_default_data_copies_once(self):
        self._write(self.bundled, "감사장", minimal_template())
        tpl.ensure_default_data()
        target = os.path.join(self.data, "templates", "감사장.json")
        self.assertTrue(os.path.exists(target))
        with open(target, "w", encoding="utf-8") as f:   # 사용자 수정
            json.dump(minimal_template(dpi=96), f)
        tpl.ensure_default_data()                        # 재실행해도 덮어쓰지 않음
        with open(target, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["dpi"], 96)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.test_template -v` → `ModuleNotFoundError`

- [ ] **Step 3: `src/app/template.py` 구현**

```python
# -*- coding: utf-8 -*-
"""템플릿 로드·검증·파라미터 스키마 (PIL 비의존 — 비Windows에서도 테스트 가능).

템플릿 JSON 스키마는 docs/superpowers/specs/2026-07-19-template-printing-design.md 참고.
"""
import json
import logging
import os
import re
import shutil
import sys

logger = logging.getLogger(__name__)

PAPER_SIZES_MM = {"A4": (210.0, 297.0)}
ELEMENT_TYPES = ("text", "image", "qr")
ALIGNS = ("left", "center", "right")
VALIGNS = ("top", "middle", "bottom")
MIN_FONT_PT = 8
DEFAULT_DPI = 300
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class TemplateError(ValueError):
    """템플릿 정의가 잘못됨"""


class TemplateNotFound(TemplateError):
    """해당 이름의 템플릿 없음"""


class TemplateParamError(ValueError):
    """요청 파라미터가 잘못됨 (API에서 400으로 변환)"""


def data_dir():
    """사용자 자원 폴더 (exe 옆 data/)"""
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "data")


def bundled_dir():
    """번들 자원 폴더 (소스: src/assets, Nuitka onefile: 추출 루트/assets)"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def _search_dirs(kind):
    return [os.path.join(data_dir(), kind), os.path.join(bundled_dir(), kind)]


def resolve_asset(kind, filename):
    """data/<kind>/ 우선, 번들 assets/<kind>/ 폴백. 없으면 None."""
    if not filename or os.path.sep in filename or "/" in filename or "\\" in filename:
        return None   # 경로 조작 방지 — 파일명만 허용
    for base in _search_dirs(kind):
        path = os.path.join(base, filename)
        if os.path.exists(path):
            return path
    return None


def ensure_default_data():
    """data/ 폴더 생성 + 번들 기본 자원을 최초 1회 복사 (있는 파일은 덮어쓰지 않음)."""
    for kind in ("templates", "backgrounds", "fonts"):
        target = os.path.join(data_dir(), kind)
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as e:
            logger.warning("data 폴더 생성 실패 (%s): %s", target, e)
            continue
        src = os.path.join(bundled_dir(), kind)
        if not os.path.isdir(src):
            continue
        for name in os.listdir(src):
            dst = os.path.join(target, name)
            if os.path.exists(dst):
                continue
            try:
                shutil.copy2(os.path.join(src, name), dst)
            except OSError as e:
                logger.warning("기본 자원 복사 실패 (%s): %s", name, e)


def _require(cond, message):
    if not cond:
        raise TemplateError(message)


def _validate_box(box):
    _require(isinstance(box, (list, tuple)) and len(box) == 4, f"box_mm은 [x,y,w,h] 4개 숫자여야 합니다: {box!r}")
    for v in box:
        _require(isinstance(v, (int, float)), f"box_mm 값은 숫자여야 합니다: {box!r}")
    _require(box[2] > 0 and box[3] > 0, f"box_mm의 폭/높이는 양수여야 합니다: {box!r}")
    return [float(v) for v in box]


def _validate_color(value, default="#000000"):
    if value is None:
        return default
    _require(isinstance(value, str) and _COLOR_RE.match(value), f"색상은 #RRGGBB 형식이어야 합니다: {value!r}")
    return value


def validate_template(data):
    """템플릿 dict 검증 + 기본값 채운 정규화 사본 반환. 실패 시 TemplateError."""
    _require(isinstance(data, dict), "템플릿 최상위는 객체여야 합니다")
    t = dict(data)

    size = t.get("size", "A4")
    if isinstance(size, str):
        _require(size in PAPER_SIZES_MM, f"지원하지 않는 용지: {size}")
    else:
        size = _validate_box([0, 0] + list(size if isinstance(size, (list, tuple)) else []))[2:]
    t["size"] = size

    orientation = t.get("orientation", "portrait")
    _require(orientation in ("portrait", "landscape"), f"orientation은 portrait/landscape: {orientation!r}")
    t["orientation"] = orientation

    dpi = t.get("dpi", DEFAULT_DPI)
    _require(isinstance(dpi, int) and 72 <= dpi <= 1200, f"dpi는 72~1200 정수여야 합니다: {dpi!r}")
    t["dpi"] = dpi

    background = t.get("background")
    _require(background is None or isinstance(background, str), "background는 파일명 문자열이어야 합니다")
    t["background"] = background

    _require(isinstance(t.get("name"), str) and t["name"].strip(), "name 필드가 필요합니다")

    elements = t.get("elements")
    _require(isinstance(elements, list) and elements, "elements는 비어있지 않은 배열이어야 합니다")
    seen_params = set()
    normalized = []
    for el in elements:
        _require(isinstance(el, dict), "요소는 객체여야 합니다")
        el = dict(el)
        el_type = el.get("type")
        _require(el_type in ELEMENT_TYPES, f"지원하지 않는 요소 type: {el_type!r}")
        param = el.get("param")
        _require(isinstance(param, str) and param.strip(), f"요소에 param이 필요합니다: {el!r}")
        _require(param not in seen_params, f"param 중복: {param}")
        seen_params.add(param)
        el["box_mm"] = _validate_box(el.get("box_mm"))
        el["required"] = bool(el.get("required", True))

        if el_type == "text":
            _require(isinstance(el.get("font"), str) and el["font"], "text 요소에 font가 필요합니다")
            size_pt = el.get("size_pt")
            _require(isinstance(size_pt, (int, float)) and size_pt >= MIN_FONT_PT,
                     f"size_pt는 {MIN_FONT_PT} 이상이어야 합니다: {size_pt!r}")
            el["size_pt"] = float(size_pt)
            el["color"] = _validate_color(el.get("color"))
            el["align"] = el.get("align", "center")
            _require(el["align"] in ALIGNS, f"align은 {ALIGNS}: {el['align']!r}")
            el["valign"] = el.get("valign", "middle")
            _require(el["valign"] in VALIGNS, f"valign은 {VALIGNS}: {el['valign']!r}")
        elif el_type == "image":
            el["fit"] = el.get("fit", "cover")
            _require(el["fit"] in ("cover", "contain"), f"fit은 cover/contain: {el['fit']!r}")
            border = el.get("border")
            if border is not None:
                _require(isinstance(border, dict), "border는 객체여야 합니다")
                width_mm = border.get("width_mm")
                _require(isinstance(width_mm, (int, float)) and width_mm > 0,
                         f"border.width_mm은 양수여야 합니다: {width_mm!r}")
                border = {"width_mm": float(width_mm), "color": _validate_color(border.get("color"))}
            el["border"] = border
        elif el_type == "qr":
            el["color"] = _validate_color(el.get("color"))

        normalized.append(el)
    t["elements"] = normalized
    return t


def page_size_mm(template):
    """(가로, 세로) mm — orientation 반영."""
    size = template["size"]
    w, h = PAPER_SIZES_MM[size] if isinstance(size, str) else (size[0], size[1])
    if template["orientation"] == "landscape":
        w, h = max(w, h), min(w, h)
    else:
        w, h = min(w, h), max(w, h)
    return (float(w), float(h))


def mm_to_px(mm, dpi):
    return int(round(mm * dpi / 25.4))


def load_template(name):
    """이름으로 템플릿 로드 (data/ 우선). 없으면 TemplateNotFound, 잘못되면 TemplateError."""
    path = resolve_asset("templates", f"{name}.json")
    if path is None:
        raise TemplateNotFound(f"템플릿을 찾을 수 없습니다: {name}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise TemplateError(f"템플릿 파일을 읽을 수 없습니다 ({name}): {e}")
    return validate_template(data)


def list_templates():
    """사용 가능한 모든 템플릿(정규화됨) — data/ 우선, 같은 파일명은 중복 제거. 잘못된 파일은 건너뜀."""
    templates = []
    seen_files = set()
    for base in _search_dirs("templates"):
        if not os.path.isdir(base):
            continue
        for filename in sorted(os.listdir(base)):
            if not filename.endswith(".json") or filename in seen_files:
                continue
            seen_files.add(filename)
            stem = filename[:-5]
            try:
                templates.append(load_template(stem))
            except TemplateError as e:
                logger.warning("템플릿 무시 (%s): %s", filename, e)
    return templates


def param_schema(template):
    """[{param, type, required}] — /templates 응답용."""
    return [{"param": el["param"], "type": el["type"], "required": el["required"]}
            for el in template["elements"]]
```

- [ ] **Step 4: 테스트 통과 확인** — `python3 -m unittest tests.test_template -v` → OK (12 tests)
- [ ] **Step 5: Commit (src repo)** — `git add app/template.py tests/test_template.py && git commit -m "feat: 템플릿 로드·검증·스키마 모듈 (PIL 비의존)"`

---

### Task 2: 번들 자산 준비 (kogongjang 이관)

**Files:**
- Create: `src/assets/templates/감사장.json`
- Create: `src/assets/backgrounds/background_kogongjang.png` (복사)
- Create: `src/assets/fonts/nanum.ttf` (복사)

- [ ] **Step 1: kogongjang 자원 확인 후 복사**

```bash
ls /mnt/c/Users/kyunghoon/projects/kogongjang-print/backgrounds/ /mnt/c/Users/kyunghoon/projects/kogongjang-print/static/fonts/ /mnt/c/Users/kyunghoon/projects/kogongjang-print/static/images/ 2>/dev/null
mkdir -p assets/templates assets/backgrounds assets/fonts
# background_kogongjang.png과 nanum.ttf의 실제 위치를 위 ls로 확인 후 복사
# (backgrounds/ 또는 static/images/에 배경, static/fonts/에 nanum.ttf가 있음)
cp <확인된 배경 경로>/background_kogongjang.png assets/backgrounds/
cp /mnt/c/Users/kyunghoon/projects/kogongjang-print/static/fonts/nanum.ttf assets/fonts/
```

파일이 예상 위치에 없으면 BLOCKED로 보고할 것 (임의 대체 금지).

- [ ] **Step 2: 감사장 템플릿 작성** — `src/assets/templates/감사장.json`
  (kogongjang pt 좌표의 mm 변환: name(20,300,500,350)pt → (7.1,105.8,176.4,123.5)mm,
  사진 (69,186)~(208,337)pt → (24.3,65.6,49.0,53.3)mm; pt×25.4/72)

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
     "align": "center", "valign": "middle", "required": true}
  ]
}
```

- [ ] **Step 3: 템플릿이 검증을 통과하는지 확인**

```bash
python3 -c "
import json
from app.template import validate_template
t = validate_template(json.load(open('assets/templates/감사장.json', encoding='utf-8')))
print('OK:', t['name'], len(t['elements']), '요소')"
```

- [ ] **Step 4: Commit (src repo)** — `git add assets && git commit -m "feat: 번들 자산 추가 (감사장 템플릿·배경·기본 한글 폰트)"`

---

### Task 3: app/compose.py — PIL+qrcode 렌더러

**Files:**
- Create: `src/app/compose.py`

WSL에서 실행 불가(Pillow 없음) — `py_compile`만. 코드 리뷰가 실질 검증이므로 아래 코드를 정확히 사용.

- [ ] **Step 1: `src/app/compose.py` 작성 (전체)**

```python
# -*- coding: utf-8 -*-
"""템플릿 조판 렌더러 — PIL + qrcode. 미리보기와 인쇄가 동일 코드 경로를 사용한다."""
import base64
import io
import logging
import re
import urllib.request

import qrcode
from PIL import Image, ImageDraw, ImageFont

from .template import (
    MIN_FONT_PT, TemplateParamError, mm_to_px, page_size_mm, resolve_asset,
)

logger = logging.getLogger(__name__)

IMAGE_FETCH_TIMEOUT = 5.0
_URL_RE = re.compile(r"^https?://", re.I)
_DATA_URI_RE = re.compile(r"^data:image/[^;]+;base64,", re.I)


def _load_image_param(value, param):
    """bytes(업로드) | http(s) URL | data:image;base64 URI → RGBA 이미지."""
    if isinstance(value, bytes):
        data = value
    elif isinstance(value, str) and _DATA_URI_RE.match(value):
        try:
            data = base64.b64decode(value.split(",", 1)[1])
        except Exception:
            raise TemplateParamError(f"base64 디코드 실패: {param}")
    elif isinstance(value, str) and _URL_RE.match(value):
        try:
            with urllib.request.urlopen(value, timeout=IMAGE_FETCH_TIMEOUT) as resp:
                data = resp.read()
        except Exception as e:
            raise TemplateParamError(f"이미지 URL 다운로드 실패 ({param}): {e}")
    else:
        raise TemplateParamError(f"이미지 파라미터는 파일 업로드, http(s) URL 또는 data URI여야 합니다: {param}")
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        raise TemplateParamError(f"유효한 이미지가 아닙니다: {param}")


def _box_px(el, dpi):
    x, y, w, h = el["box_mm"]
    return (mm_to_px(x, dpi), mm_to_px(y, dpi), mm_to_px(w, dpi), mm_to_px(h, dpi))


def _draw_image_element(canvas, el, value, dpi):
    img = _load_image_param(value, el["param"])
    x, y, w, h = _box_px(el, dpi)

    if el["fit"] == "cover":
        scale = max(w / img.width, h / img.height)
        resized = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))
        left = (resized.width - w) // 2
        top = (resized.height - h) // 2
        fitted = resized.crop((left, top, left + w, top + h))
        canvas.paste(fitted, (x, y), fitted)
    else:  # contain — 박스 안에 비율 유지로 중앙 배치
        scale = min(w / img.width, h / img.height)
        resized = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))
        ox = x + (w - resized.width) // 2
        oy = y + (h - resized.height) // 2
        canvas.paste(resized, (ox, oy), resized)

    if el["border"]:
        bw = max(1, mm_to_px(el["border"]["width_mm"], dpi))
        draw = ImageDraw.Draw(canvas)
        for i in range(bw):
            draw.rectangle([x + i, y + i, x + w - 1 - i, y + h - 1 - i],
                           outline=el["border"]["color"])


def _load_font(font_name, size_px):
    path = resolve_asset("fonts", font_name)
    if path is None:
        raise TemplateParamError(f"폰트를 찾을 수 없습니다: {font_name}")
    return ImageFont.truetype(path, size_px)


def _wrap_lines(draw, text, font, max_width):
    """단어 단위 줄바꿈 (한국어는 공백 기준 + 초과 시 글자 단위 분할)."""
    lines = []
    for raw_line in text.splitlines() or [""]:
        current = ""
        for chunk in raw_line.split(" "):
            candidate = f"{current} {chunk}".strip()
            if draw.textlength(candidate, font=font) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = chunk
        # 공백 없는 긴 문자열은 글자 단위로 자름
        while current and draw.textlength(current, font=font) > max_width:
            cut = len(current)
            while cut > 1 and draw.textlength(current[:cut], font=font) > max_width:
                cut -= 1
            lines.append(current[:cut])
            current = current[cut:]
        lines.append(current)
    return lines


def _draw_text_element(canvas, el, text, dpi):
    x, y, w, h = _box_px(el, dpi)
    draw = ImageDraw.Draw(canvas)

    size_pt = el["size_pt"]
    while True:
        size_px = max(1, round(size_pt * dpi / 72))
        font = _load_font(el["font"], size_px)
        lines = _wrap_lines(draw, text, font, w)
        ascent, descent = font.getmetrics()
        line_height = ascent + descent
        total_height = line_height * len(lines)
        if total_height <= h or size_pt <= MIN_FONT_PT:
            break
        size_pt -= 1   # 박스를 넘으면 폰트를 1pt씩 축소 (최소 MIN_FONT_PT)

    if el["valign"] == "top":
        ty = y
    elif el["valign"] == "bottom":
        ty = y + h - total_height
    else:
        ty = y + (h - total_height) // 2

    for line in lines:
        line_width = draw.textlength(line, font=font)
        if el["align"] == "left":
            tx = x
        elif el["align"] == "right":
            tx = x + w - line_width
        else:
            tx = x + (w - line_width) / 2
        draw.text((tx, ty), line, font=font, fill=el["color"])
        ty += line_height


def _draw_qr_element(canvas, el, data, dpi):
    x, y, w, h = _box_px(el, dpi)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    side = min(w, h)
    module = side / n
    ox = x + (w - side) // 2
    oy = y + (h - side) // 2
    draw = ImageDraw.Draw(canvas)
    for row in range(n):
        for col in range(n):
            if matrix[row][col]:
                draw.rectangle([
                    round(ox + col * module), round(oy + row * module),
                    round(ox + (col + 1) * module) - 1, round(oy + (row + 1) * module) - 1,
                ], fill=el["color"])


def render(template, params):
    """정규화된 템플릿 + 파라미터 → RGB PIL.Image. 파라미터 문제는 TemplateParamError."""
    dpi = template["dpi"]
    w_mm, h_mm = page_size_mm(template)
    canvas = Image.new("RGB", (mm_to_px(w_mm, dpi), mm_to_px(h_mm, dpi)), "white")

    if template["background"]:
        bg_path = resolve_asset("backgrounds", template["background"])
        if bg_path is None:
            raise TemplateParamError(f"배경 파일을 찾을 수 없습니다: {template['background']}")
        with Image.open(bg_path) as bg:
            canvas.paste(bg.convert("RGB").resize(canvas.size))

    for el in template["elements"]:
        value = params.get(el["param"])
        if isinstance(value, str):
            value = value.strip() or None
        if value is None:
            if el["required"]:
                raise TemplateParamError(f"필수 파라미터가 없습니다: {el['param']}")
            continue
        if el["type"] == "text":
            _draw_text_element(canvas, el, str(value), dpi)
        elif el["type"] == "image":
            _draw_image_element(canvas, el, value, dpi)
        elif el["type"] == "qr":
            _draw_qr_element(canvas, el, str(value), dpi)

    return canvas
```

- [ ] **Step 2: 검증** — `python3 -m py_compile app/compose.py`
- [ ] **Step 3: Commit (src repo)** — `git add app/compose.py && git commit -m "feat: PIL+qrcode 조판 렌더러 (텍스트 자동줄바꿈·축소, cover/contain, QR)"`

---

### Task 4: API 3종 추가

**Files:**
- Modify: `src/app/api.py` (끝에 추가 + import 보강)

- [ ] **Step 1: import 추가** — 기존 import 블록에:

```python
from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from . import compose
from . import template as tpl
```

- [ ] **Step 2: 파일 끝에 엔드포인트 3개 + 헬퍼 추가**

```python
# ============================================================
# 템플릿 조판 인쇄 (v2.5.0)
# ============================================================

PREVIEW_DPI = 150
PREVIEW_DPI_MAX = 600


def _render_to_png_file(template, params):
    """조판 후 PNG 임시 파일 경로 반환 (스레드풀에서 실행)."""
    image = compose.render(template, params)
    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        image.save(tmp_path, "PNG", dpi=(template["dpi"], template["dpi"]))
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return tmp_path


@api.get("/templates")
def list_templates():
    """사용 가능한 조판 템플릿 목록 + 파라미터 스키마"""
    templates = tpl.list_templates()
    return {
        "templates": [
            {"name": t["name"], "size": t["size"], "dpi": t["dpi"],
             "orientation": t["orientation"], "params": tpl.param_schema(t)}
            for t in templates
        ],
        "count": len(templates),
    }


def _load_template_or_http_error(name):
    try:
        return tpl.load_template(name)
    except tpl.TemplateNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except tpl.TemplateError as e:
        raise HTTPException(status_code=400, detail=f"템플릿 정의 오류: {e}")


@api.post("/print-template")
async def print_template(request: Request):
    """템플릿 조판 인쇄. multipart/form-data:
    template(필수)·printer(선택)·요소 파라미터(텍스트/QR=문자열, 이미지=파일 또는 URL/base64)"""
    form = await request.form()

    template_name = form.get("template")
    if not isinstance(template_name, str) or not template_name.strip():
        raise HTTPException(status_code=400, detail="template 필드가 필요합니다.")
    template = _load_template_or_http_error(template_name.strip())

    printer = form.get("printer")
    printer = printer.strip() if isinstance(printer, str) else ""
    target_printer = printer or get_selected_printer() or printing.get_default_printer()
    if not target_printer:
        raise HTTPException(status_code=400, detail="사용 가능한 프린터가 없습니다.")
    if not printing.printer_exists(target_printer):
        raise HTTPException(status_code=400, detail=f"프린터를 찾을 수 없습니다: {target_printer}")

    params = {}
    for key, value in form.multi_items():
        if key in ("template", "printer"):
            continue
        params[key] = value if isinstance(value, str) else await value.read()

    try:
        tmp_path = await run_in_threadpool(_render_to_png_file, template, params)
    except tpl.TemplateParamError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = jobs.submit(tmp_path, target_printer, filename=f"{template['name']}.png")
    return {
        "status": "queued",
        "template": template["name"],
        "printer": target_printer,
        "job_id": job_id,
    }


@api.get("/preview-template")
async def preview_template(request: Request):
    """조판 미리보기 PNG. 쿼리: template(필수), dpi(선택, 기본 150),
    텍스트/QR 파라미터는 문자열, 이미지 파라미터는 URL 또는 data URI"""
    query = dict(request.query_params)

    template_name = (query.pop("template", "") or "").strip()
    if not template_name:
        raise HTTPException(status_code=400, detail="template 파라미터가 필요합니다.")
    template = _load_template_or_http_error(template_name)

    dpi_raw = query.pop("dpi", None)
    dpi = PREVIEW_DPI
    if dpi_raw is not None:
        try:
            dpi = max(72, min(PREVIEW_DPI_MAX, int(dpi_raw)))
        except ValueError:
            raise HTTPException(status_code=400, detail="dpi는 정수여야 합니다.")
    template = {**template, "dpi": dpi}

    def _render_bytes():
        image = compose.render(template, query)
        buf = io.BytesIO()
        image.save(buf, "PNG")
        return buf.getvalue()

    try:
        png = await run_in_threadpool(_render_bytes)
    except tpl.TemplateParamError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(content=png, media_type="image/png")
```

`import io`가 api.py 상단에 없으면 추가.

- [ ] **Step 3: 검증** — `python3 -m py_compile app/api.py` + `python3 -m unittest discover -s tests` (기존 전체 green)
- [ ] **Step 4: Commit (src repo)** — `git add app/api.py && git commit -m "feat: 템플릿 조판 API (/templates, /print-template, /preview-template)"`

---

### Task 5: 초기화·빌드·의존성 연결

**Files:**
- Modify: `src/app/gui.py` (`jobs.start()` 직전에 1줄)
- Modify: `src/build_release.py`
- Modify: `src/requirements.txt`

- [ ] **Step 1: gui.py `__init__`의 `jobs.start()` 위에 추가**

```python
        # 템플릿·배경·폰트 기본 자원 준비 (data/ 폴더)
        tpl.ensure_default_data()
```

import 블록에 `from . import template as tpl` 추가.

- [ ] **Step 2: build_release.py** — `--include-package=app` 라인 아래에:

```python
        "--include-package=qrcode",
        # 번들 자산 (템플릿·배경·폰트)
        "--include-data-dir=assets=assets",
```

- [ ] **Step 3: requirements.txt에 `qrcode` 추가** (customtkinter 다음 줄)

- [ ] **Step 4: 검증 + Commit (src repo)**

```bash
python3 -m py_compile app/gui.py build_release.py && python3 -m unittest discover -s tests
git add app/gui.py build_release.py requirements.txt
git commit -m "feat: 템플릿 자원 초기화·qrcode 의존성·번들 자산 빌드 연결"
```

---

### Task 6: 버전 2.5.0 + 문서

**Files:**
- Modify: `src/app/__init__.py` (VERSION = "2.5.0")
- Modify: `src/app/changelog.py` (2.5.0 항목 맨 앞)
- Modify: `CHANGELOG.md`, `README.md`, `docs/smoke-test.md`, `CLAUDE.md` (외부 repo)

- [ ] **Step 1: VERSION을 "2.5.0"으로 변경, changelog.py 맨 앞에 추가**

```python
    ("2.5.0", "2026-07-19", [
        "[추가] 템플릿 조판 인쇄 — JSON 템플릿(텍스트·이미지·QR코드)으로 감사장 등 문서를 조판해 인쇄",
        "[추가] GET /templates, POST /print-template, GET /preview-template API",
        "[추가] 감사장 템플릿 기본 제공 (kogongjang-print 대체)",
        "[추가] data/ 폴더 — 사용자 템플릿·배경·폰트 관리",
    ]),
```

- [ ] **Step 2: 외부 CHANGELOG.md 맨 위에 동일 내용의 v2.5.0 섹션 추가**

```markdown
## v2.5.0 (2026-07-19)

- 템플릿 조판 인쇄 추가 — JSON 템플릿(텍스트·이미지·QR코드)으로 감사장 등 문서를 조판해 인쇄
- 신규 API: `GET /templates`, `POST /print-template`, `GET /preview-template`(PNG 미리보기)
- 감사장 템플릿 기본 제공 (kogongjang-print 통합·대체)
- exe 옆 `data/` 폴더에서 사용자 템플릿·배경·폰트 관리
```

- [ ] **Step 3: README.md API 표에 3행 추가**

```markdown
| `GET /templates` | 조판 템플릿 목록 |
| `POST /print-template` | 템플릿 조판 인쇄 (감사장 등) |
| `GET /preview-template` | 조판 미리보기 (PNG) |
```

- [ ] **Step 4: docs/smoke-test.md에 섹션 추가**

```markdown
## 템플릿 조판 (v2.5.0)
- [ ] `GET /templates` → 감사장 템플릿 + 파라미터 스키마(photo/name) 반환
- [ ] 브라우저에서 `/preview-template?template=감사장&name=홍길동` → 배경+이름 조판 PNG 표시
- [ ] `POST /print-template` (name=홍길동, photo 파일 첨부) → 실제 인쇄물 = 미리보기와 일치
- [ ] photo 생략 인쇄 → 사진 없이 정상 인쇄 (required=false)
- [ ] name 생략 → 400 "필수 파라미터가 없습니다: name"
- [ ] QR 요소가 있는 템플릿 → 인쇄물의 QR이 휴대폰으로 스캔됨
- [ ] `data/templates/`의 JSON 수정 → 재요청 시 즉시 반영 (재시작 불필요)
- [ ] 최초 실행 시 data/ 폴더에 기본 템플릿·배경·폰트 복사됨
```

- [ ] **Step 5: CLAUDE.md** — Architecture 목록에 `template.py`/`compose.py` 항목, API 표 3행, Key Details에 템플릿 스키마 문서 포인터 추가:

```markdown
- `template.py` — template JSON load/validate/schema (PIL-free, WSL-testable); user assets in `data/`, bundled in `assets/`
- `compose.py` — PIL+qrcode renderer (text wrap/shrink, cover/contain images, QR) — same code path for preview and print
```

Key Implementation Details에:

```markdown
- **Template schema**: see `docs/superpowers/specs/2026-07-19-template-printing-design.md`; coordinates in mm, fonts/backgrounds resolved from `data/` first then bundled `assets/`
```

- [ ] **Step 6: 검증 + 커밋** — src: `python3 -m unittest discover -s tests` 후
  `git add app/__init__.py app/changelog.py && git commit -m "chore: v2.5.0 버전·릴리스 노트"`;
  외부: `git add CHANGELOG.md README.md docs/smoke-test.md CLAUDE.md && git commit -m "docs: v2.5.0 템플릿 조판 문서 반영" (트레일러 포함)`

---

### Task 7: 모의 서버 동기화 + WSL 검증

**Files:**
- Modify: `dev/printer_mock.py` (외부 repo)

- [ ] **Step 1: mock에 템플릿 엔드포인트 3개 추가**

`printer_mock.py`에 상수 추가 (PRINTERS 아래):

```python
# 실서버의 감사장 템플릿과 동일한 스키마 (모의)
TEMPLATES = [{
    "name": "감사장", "size": "A4", "dpi": 300, "orientation": "portrait",
    "params": [
        {"param": "photo", "type": "image", "required": False},
        {"param": "name", "type": "text", "required": True},
    ],
}]

# 미리보기용 placeholder PNG (1x1 회색)
PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNsaGj4DwAFhAJ/l6i5FwAAAABJRU5ErkJggg=="
)
```

(파일 상단 import에 `base64` 추가)

`do_GET`에 분기 추가 (`/printers` 아래):

```python
        elif self.path.split("?")[0] == "/templates":
            self._send_json(200, {"templates": TEMPLATES, "count": len(TEMPLATES)})
        elif self.path.split("?")[0] == "/preview-template":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            name = (q.get("template", [""])[0]).strip()
            if name != "감사장":
                self._send_json(404, {"detail": f"템플릿을 찾을 수 없습니다: {name}"})
                return
            if not (q.get("name", [""])[0]).strip():
                self._send_json(400, {"detail": "필수 파라미터가 없습니다: name"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PLACEHOLDER_PNG)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(PLACEHOLDER_PNG)
```

`do_POST`에 분기 추가:

```python
        elif self.path == "/print-template":
            self._handle_print_template()
```

핸들러 추가 (`_handle_print_image` 아래):

```python
    def _handle_print_template(self):
        length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json(400, {"detail": "multipart/form-data 요청이 필요합니다."})
            return
        fields = parse_multipart(self.rfile.read(length), content_type)

        template = ""
        if "template" in fields:
            template = fields["template"][1].decode("utf-8", errors="replace").strip()
        if not template:
            self._send_json(400, {"detail": "template 필드가 필요합니다."})
            return
        if template != "감사장":
            self._send_json(404, {"detail": f"템플릿을 찾을 수 없습니다: {template}"})
            return
        if "name" not in fields or not fields["name"][1].decode("utf-8", errors="replace").strip():
            self._send_json(400, {"detail": "필수 파라미터가 없습니다: name"})
            return

        printer_field = fields.get("printer")
        printer = printer_field[1].decode("utf-8", errors="replace").strip() if printer_field else ""
        target_printer = printer or PRINTER_OK
        if target_printer not in [p["name"] for p in PRINTERS]:
            self._send_json(400, {"detail": f"프린터를 찾을 수 없습니다: {target_printer}"})
            return

        job_id = submit_job(f"{template}.png", target_printer, PLACEHOLDER_PNG, ".png")
        self._send_json(200, {
            "status": "queued", "template": template,
            "printer": target_printer, "job_id": job_id,
        })
```

배너의 엔드포인트 줄에 `GET /templates · POST /print-template · GET /preview-template` 추가.
파일 헤더의 계약 버전 주석을 v2.5.0으로 갱신.

- [ ] **Step 2: WSL 검증 (curl)**

```bash
python3 -m py_compile dev/printer_mock.py
python3 dev/printer_mock.py --port 8124 --delay 1 --no-preview &
sleep 1
curl -s localhost:8124/templates                                        # 감사장 + params 2개
curl -s "localhost:8124/preview-template?template=감사장&name=홍길동" -o /tmp/p.png -w '%{http_code} %{content_type}\n'   # 200 image/png
curl -s -w ' [%{http_code}]' "localhost:8124/preview-template?template=감사장"   # 400 필수 파라미터
curl -s -F template=감사장 -F name=홍길동 localhost:8124/print-template          # queued + job_id + template
curl -s -w ' [%{http_code}]' -F template=없음 -F name=x localhost:8124/print-template   # 404
kill %1; rm -rf mock-prints /tmp/p.png
```

- [ ] **Step 3: Commit (외부 repo, 트레일러 포함)** — `git add dev/printer_mock.py && git commit -m "feat: 모의 서버에 템플릿 조판 API 반영 (v2.5.0 계약)"`

---

### Task 8: 최종 검증

- [ ] **Step 1: src 전체** — `python3 -m unittest discover -s tests -v` (전체 green, 34개±)
  + `python3 -m py_compile printer_server.py app/*.py build_release.py`
- [ ] **Step 2: 외부 repo push** — `git push origin main`
- [ ] **Step 3: 사용자 안내** — Windows에서 `pip install qrcode` 후 소스 실행 스모크
  (smoke-test.md의 v2.5.0 섹션) → 통과 시 빌드 → 릴리스는 `scripts/publish_release.sh`

---

## 자체 리뷰

- 스펙 커버리지: 스키마·검증(T1), 자산·마이그레이션(T2), 렌더러 3요소·이미지 입력 3형식·축소 로직(T3), API 3종·오류 형식·preview dpi(T4), data/ 초기화·빌드·qrcode(T5), 버전·문서·스모크(T6), 모의 서버 동기화(T7) — 스펙 전 섹션에 대응 태스크 존재. 스코프 제외(템플릿 GUI, PDF, kogongjang 라우트) 미구현 확인
- 타입 일관성: `validate_template` 정규화 필드(`border` None 가능, `size` str|list)를 compose가 동일 가정으로 소비; `TemplateNotFound ⊂ TemplateError`, `TemplateParamError` 분리 — api의 예외 매핑과 일치; `jobs.submit(path, printer, filename)` 기존 시그니처 그대로
- 플레이스홀더 없음 (Task 2의 자원 경로만 실행 시 ls로 확정 — 파일 부재 시 BLOCKED 규칙 명시)
