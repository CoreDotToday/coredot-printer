# 템플릿 레이아웃 편집기 (v2.7.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 템플릿 탭을 좌(편집)/우(라이브 미리보기) 2단 편집기로 개편 — 요소 위치·텍스트 속성을 GUI에서 조정하고 저장한다 (v2.7.0).

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-19-template-editor-design.md`. `app/template.py`에 `id`/`list_assets`/`save_template` 추가(WSL TDD). `app/gui.py` 템플릿 탭 재구성: 작업 사본 편집 + tk 변수 trace → 300ms 디바운스 → `compose.render()`(dpi 72) 백그라운드 렌더 + 세대 토큰 → CTkImage 표시, 가이드 박스는 GUI에서 PIL 오버레이.

**Tech Stack:** 기존 스택 그대로 (신규 의존성 없음). API 무변경 → 모의 서버 갱신 불필요.

**환경·관례:** WSL은 template.py unittest + py_compile까지. src 커밋 한 줄·트레일러 없음, 외부 repo 문서 커밋은 트레일러 포함.

---

### Task 1: app/template.py 확장 (TDD)

**Files:**
- Modify: `src/app/template.py`
- Test: `src/tests/test_template.py` (클래스 추가)

- [ ] **Step 1: 실패하는 테스트 추가** — `tests/test_template.py` 끝(기존 `if __name__` 위)에:

```python
class AssetAndSaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        self.bundled = os.path.join(self.tmp, "assets")
        for base in (self.data, self.bundled):
            for kind in ("templates", "backgrounds", "fonts"):
                os.makedirs(os.path.join(base, kind))
        self.p1 = mock.patch.object(tpl, "data_dir", lambda: self.data)
        self.p2 = mock.patch.object(tpl, "bundled_dir", lambda: self.bundled)
        self.p1.start(); self.p2.start()

    def tearDown(self):
        self.p1.stop(); self.p2.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_template(self, base, stem, data):
        with open(os.path.join(base, "templates", stem + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_load_template_sets_id_from_filename(self):
        self._write_template(self.data, "파일명", minimal_template())  # name 필드는 "테스트"
        t = tpl.load_template("파일명")
        self.assertEqual(t["id"], "파일명")
        self.assertEqual(t["name"], "테스트")

    def test_list_assets_merges_dedups_sorts(self):
        open(os.path.join(self.data, "backgrounds", "b.png"), "w").close()
        open(os.path.join(self.data, "backgrounds", "a.png"), "w").close()
        open(os.path.join(self.bundled, "backgrounds", "a.png"), "w").close()
        open(os.path.join(self.bundled, "backgrounds", "c.png"), "w").close()
        self.assertEqual(tpl.list_assets("backgrounds"), ["a.png", "b.png", "c.png"])

    def test_save_template_roundtrip_without_id_key(self):
        saved = tpl.save_template("감사장사본", minimal_template())
        self.assertEqual(saved["id"], "감사장사본")
        path = os.path.join(self.data, "templates", "감사장사본.json")
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertNotIn("id", on_disk)
        self.assertEqual(tpl.load_template("감사장사본")["name"], "테스트")

    def test_save_template_strips_id_from_input(self):
        data = minimal_template()
        data["id"] = "무시됨"
        tpl.save_template("실제이름", data)
        with open(os.path.join(self.data, "templates", "실제이름.json"), encoding="utf-8") as f:
            self.assertNotIn("id", json.load(f))

    def test_save_template_rejects_bad_id(self):
        for bad in ("../x", "a/b", "C:evil", "", ".."):
            with self.assertRaises(tpl.TemplateError):
                tpl.save_template(bad, minimal_template())

    def test_save_template_rejects_invalid_data(self):
        with self.assertRaises(tpl.TemplateError):
            tpl.save_template("x", {"elements": "broken"})
        self.assertFalse(os.path.exists(os.path.join(self.data, "templates", "x.json")))

    def test_save_leaves_no_tmp_files(self):
        tpl.save_template("정상", minimal_template())
        leftovers = [f for f in os.listdir(os.path.join(self.data, "templates")) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])
```

- [ ] **Step 2: 실패 확인** — `python3 -m unittest tests.test_template -v` → 신규 테스트들 ERROR (속성 없음)

- [ ] **Step 3: `app/template.py` 구현**

상단 import에 `import tempfile` 추가. `resolve_asset`의 인라인 가드를 공용 헬퍼로 추출:

```python
def _is_safe_name(name):
    """경로 조작 방지 — 순수 파일명(확장자 유무 무관)만 허용."""
    return bool(name) and os.path.basename(name) == name and ":" not in name and name not in (".", "..")
```

`resolve_asset`의 기존 가드 블록을 `if not _is_safe_name(filename): return None`으로 교체 (동작 동일).

`load_template` 마지막 줄을 다음으로 변경:

```python
    normalized = validate_template(data)
    normalized["id"] = name   # 저장 대상 파일명 스템 (name 필드와 다를 수 있음)
    return normalized
```

신규 함수 2개 (`param_schema` 아래):

```python
def list_assets(kind):
    """data/<kind> + 번들 <kind>의 파일명 합집합 (숨김 파일 제외, 정렬)."""
    names = set()
    for base in _search_dirs(kind):
        if os.path.isdir(base):
            names.update(n for n in os.listdir(base) if not n.startswith("."))
    return sorted(names)


def save_template(template_id, data):
    """검증 후 data/templates/<id>.json에 원자적 저장. 정규화된 dict(id 포함) 반환."""
    if not _is_safe_name(template_id):
        raise TemplateError(f"잘못된 템플릿 이름입니다: {template_id!r}")
    payload = {k: v for k, v in data.items() if k != "id"}
    normalized = validate_template(payload)

    target_dir = os.path.join(data_dir(), "templates")
    os.makedirs(target_dir, exist_ok=True)
    to_write = {k: v for k, v in normalized.items() if k != "id"}
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(to_write, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, os.path.join(target_dir, f"{template_id}.json"))
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    normalized["id"] = template_id
    return normalized
```

주의: `validate_template`는 `id`를 모르는 상태 유지(정규화 dict에 id를 넣는 것은 load/save 계층).
`list_templates`는 `load_template`을 쓰므로 자동으로 id가 붙는다 — 기존 테스트 영향 없음 확인.

- [ ] **Step 4: 전체 테스트** — `python3 -m unittest discover -s tests -v` → 43개 green (36 + 7)
- [ ] **Step 5: Commit (src)** — `git add app/template.py tests/test_template.py && git commit -m "feat: 템플릿 id·자산 목록·원자적 저장 (편집기 기반)"`

---

### Task 2: gui.py 템플릿 탭 편집기 개편

**Files:**
- Modify: `src/app/gui.py`

- [ ] **Step 1: import·상수 추가**

```python
import copy
from PIL import Image, ImageDraw   # 가이드 박스 오버레이·썸네일용 (compose가 이미 PIL 의존)
```

모듈 상수(`SERVER_POLL_MAX` 아래):

```python
LIVE_PREVIEW_DEBOUNCE_MS = 300   # 편집 중 미리보기 재렌더 디바운스
LIVE_PREVIEW_DPI = 72            # 내장 미리보기 렌더 해상도 (A4 → 595×842px)
PREVIEW_MAX_W = 250              # 미리보기 표시 최대 폭(px)
PREVIEW_MAX_H = 340              # 미리보기 표시 최대 높이(px)
```

- [ ] **Step 2: `__init__` 템플릿 상태 블록 교체** — 기존 `# 템플릿 탭 상태` 블록을:

```python
        # 템플릿 탭 상태
        self._templates = {}               # name → 정규화된 템플릿 (id 포함)
        self._template_param_widgets = {}  # param → {"type", "widget"|"path_var"}
        self._template_busy = False        # 크게 보기/테스트 인쇄 재진입 방지
        self._working_template = None      # 편집 중 작업 사본 (deepcopy)
        self._template_dirty = False       # 미저장 편집 여부
        self._suspend_traces = False       # 프로그램적 값 설정 중 trace 무시
        self._live_after_id = None         # 디바운스 예약 id
        self._live_generation = 0          # 낡은 렌더 폐기용 세대 토큰
        self._preview_ctk_image = None     # CTkImage 참조 유지 (GC 방지)
        # 요소 편집 필드 변수
        self._el_x_var = tk.StringVar(); self._el_y_var = tk.StringVar()
        self._el_w_var = tk.StringVar(); self._el_h_var = tk.StringVar()
        self._el_size_var = tk.StringVar(); self._el_font_var = tk.StringVar()
        self._el_align_var = tk.StringVar(); self._el_valign_var = tk.StringVar()
        self._bg_var = tk.StringVar()
        self._guide_var = tk.BooleanVar(value=True)
        for var in (self._el_x_var, self._el_y_var, self._el_w_var, self._el_h_var,
                    self._el_size_var, self._el_font_var, self._el_align_var,
                    self._el_valign_var, self._bg_var):
            var.trace_add("write", lambda *_: self._on_edit_field_changed())
```

- [ ] **Step 3: `_build_template_tab` 전체 교체**

```python
    def _build_template_tab(self, parent):
        select_row = ctk.CTkFrame(parent, fg_color="transparent")
        select_row.pack(fill='x', padx=10, pady=(8, 4))
        ctk.CTkLabel(select_row, text="템플릿:", font=ctk.CTkFont(family="맑은 고딕", size=12)).pack(side='left', padx=5)
        self.template_combo = ctk.CTkComboBox(
            select_row, state='readonly', width=200,
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            command=self._on_template_selected
        )
        self.template_combo.pack(side='left', padx=5)
        ctk.CTkButton(
            select_row, text="새로고침", command=self._refresh_templates,
            font=ctk.CTkFont(family="맑은 고딕", size=12),
            fg_color="#FFC107", text_color="black", hover_color="#FFD54F",
            width=80, corner_radius=6
        ).pack(side='left', padx=5)

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill='both', expand=True, padx=10, pady=4)

        # ── 좌열: 편집 컨트롤 (스크롤) ──
        left = ctk.CTkScrollableFrame(body, width=360, fg_color="transparent")
        left.pack(side='left', fill='both', expand=True)

        f11 = ctk.CTkFont(family="맑은 고딕", size=11)
        f12 = ctk.CTkFont(family="맑은 고딕", size=12)

        bg_row = ctk.CTkFrame(left, fg_color="transparent")
        bg_row.pack(fill='x', pady=2)
        ctk.CTkLabel(bg_row, text="배경:", width=60, anchor='w', font=f12).pack(side='left', padx=2)
        self.bg_combo = ctk.CTkComboBox(bg_row, state='readonly', width=230, font=f11,
                                        variable=self._bg_var)
        self.bg_combo.pack(side='left', padx=2)

        el_row = ctk.CTkFrame(left, fg_color="transparent")
        el_row.pack(fill='x', pady=2)
        ctk.CTkLabel(el_row, text="요소:", width=60, anchor='w', font=f12).pack(side='left', padx=2)
        self.element_combo = ctk.CTkComboBox(el_row, state='readonly', width=230, font=f11,
                                             command=self._on_element_selected)
        self.element_combo.pack(side='left', padx=2)

        pos_row = ctk.CTkFrame(left, fg_color="transparent")
        pos_row.pack(fill='x', pady=2)
        ctk.CTkLabel(pos_row, text="위치(mm):", width=60, anchor='w', font=f11).pack(side='left', padx=2)
        for label, var in (("X", self._el_x_var), ("Y", self._el_y_var),
                           ("W", self._el_w_var), ("H", self._el_h_var)):
            ctk.CTkLabel(pos_row, text=label, font=f11).pack(side='left', padx=(6, 1))
            ctk.CTkEntry(pos_row, textvariable=var, width=52, font=f11).pack(side='left')

        # text 요소 전용 (선택 요소가 text가 아니면 pack_forget)
        self.text_edit_frame = ctk.CTkFrame(left, fg_color="transparent")
        self.text_edit_frame.pack(fill='x', pady=2)
        ctk.CTkLabel(self.text_edit_frame, text="크기(pt):", width=60, anchor='w', font=f11).pack(side='left', padx=2)
        ctk.CTkEntry(self.text_edit_frame, textvariable=self._el_size_var, width=52, font=f11).pack(side='left')
        ctk.CTkLabel(self.text_edit_frame, text="폰트:", font=f11).pack(side='left', padx=(8, 1))
        self.font_combo = ctk.CTkComboBox(self.text_edit_frame, state='readonly', width=130,
                                          font=f11, variable=self._el_font_var)
        self.font_combo.pack(side='left')
        ctk.CTkLabel(self.text_edit_frame, text="정렬:", font=f11).pack(side='left', padx=(8, 1))
        ctk.CTkComboBox(self.text_edit_frame, state='readonly', width=70, font=f11,
                        values=["left", "center", "right"],
                        variable=self._el_align_var).pack(side='left')
        ctk.CTkComboBox(self.text_edit_frame, state='readonly', width=75, font=f11,
                        values=["top", "middle", "bottom"],
                        variable=self._el_valign_var).pack(side='left', padx=(4, 0))

        opt_row = ctk.CTkFrame(left, fg_color="transparent")
        opt_row.pack(fill='x', pady=2)
        ctk.CTkCheckBox(opt_row, text="영역 가이드 표시", variable=self._guide_var,
                        command=self._schedule_live_preview, font=f11).pack(side='left', padx=2)
        ctk.CTkButton(opt_row, text="레이아웃 저장", command=self._save_layout,
                      font=ctk.CTkFont(family="맑은 고딕", size=12, weight="bold"),
                      fg_color="#4CAF50", hover_color="#66BB6A",
                      width=110, corner_radius=6).pack(side='right', padx=2)

        ctk.CTkLabel(left, text="─ 인쇄 파라미터 (미리보기 샘플값 겸용) ─",
                     font=f11, text_color="gray").pack(pady=(8, 0))
        self.template_params_frame = ctk.CTkFrame(left, fg_color="transparent")
        self.template_params_frame.pack(fill='x', pady=2)

        action_row = ctk.CTkFrame(left, fg_color="transparent")
        action_row.pack(fill='x', pady=4)
        self.template_preview_button = ctk.CTkButton(
            action_row, text="크게 보기", command=self._template_preview,
            font=ctk.CTkFont(family="맑은 고딕", size=12, weight="bold"),
            fg_color="#2196F3", hover_color="#42A5F5", width=100, corner_radius=6
        )
        self.template_preview_button.pack(side='left', padx=3)
        self.template_print_button = ctk.CTkButton(
            action_row, text="테스트 인쇄", command=self._template_test_print,
            font=ctk.CTkFont(family="맑은 고딕", size=12, weight="bold"),
            fg_color="#4CAF50", hover_color="#66BB6A", width=100, corner_radius=6
        )
        self.template_print_button.pack(side='left', padx=3)

        folder_row = ctk.CTkFrame(left, fg_color="transparent")
        folder_row.pack(fill='x', pady=(0, 4))
        for label, kind in (("템플릿 폴더", "templates"), ("배경 폴더", "backgrounds"), ("폰트 폴더", "fonts")):
            ctk.CTkButton(folder_row, text=label,
                          command=lambda k=kind: self._open_data_folder(k),
                          font=f11, fg_color="gray25", hover_color="gray35",
                          width=85, corner_radius=6).pack(side='left', padx=3)

        # ── 우열: 내장 미리보기 ──
        right = ctk.CTkFrame(body, fg_color="gray17", corner_radius=8)
        right.pack(side='left', fill='y', padx=(8, 0))
        ctk.CTkLabel(right, text="미리보기", font=ctk.CTkFont(family="맑은 고딕", size=12, weight="bold")).pack(pady=(8, 2))
        self.preview_label = ctk.CTkLabel(right, text="(템플릿 없음)", width=PREVIEW_MAX_W,
                                          height=PREVIEW_MAX_H, font=f11, text_color="gray")
        self.preview_label.pack(padx=10, pady=4)
        self.preview_status = ctk.CTkLabel(right, text="", font=ctk.CTkFont(family="맑은 고딕", size=10),
                                           text_color="gray", wraplength=PREVIEW_MAX_W)
        self.preview_status.pack(pady=(0, 8))

        self._refresh_templates()
```

- [ ] **Step 4: 선택·편집·저장 메서드 교체/추가**

`_on_template_selected` 전체 교체 + 신규 메서드들 (기존 `_refresh_templates`/`_apply_templates`는 유지하되 아래 두 곳 수정 — ① `_refresh_templates` 시작부에 dirty 가드 추가, ② `_apply_templates`의 `self._on_template_selected(None)` 경로는 그대로):

```python
    def _refresh_templates(self):
        """템플릿 목록을 백그라운드에서 로드해 콤보 갱신."""
        if not self._confirm_discard_changes():
            return
        def worker():
            try:
                templates = {t["name"]: t for t in tpl.list_templates()}
            except Exception as e:
                logger.warning("템플릿 목록 로드 실패: %s", e)
                templates = {}
            self.root.after(0, lambda: self._apply_templates(templates))
        threading.Thread(target=worker, daemon=True).start()

    def _confirm_discard_changes(self):
        """미저장 편집이 있으면 확인. True=계속 진행."""
        if not self._template_dirty:
            return True
        if messagebox.askyesno("변경 사항", "저장하지 않은 레이아웃 변경이 있습니다. 버리고 계속할까요?"):
            self._template_dirty = False
            return True
        return False

    def _on_template_selected(self, name):
        """작업 사본 생성 + 편집 필드·파라미터 폼 재구성."""
        if not self._confirm_discard_changes():
            # 콤보 표시를 현재 작업 사본으로 되돌림
            if self._working_template is not None:
                self.template_combo.set(self._working_template["name"])
            return
        template = self._templates.get(name) if name else None
        self._working_template = copy.deepcopy(template) if template else None
        self._template_dirty = False

        # 파라미터 폼 재구성 (기존 로직 + 라이브 미리보기 trace)
        for child in self.template_params_frame.winfo_children():
            child.destroy()
        self._template_param_widgets = {}

        self._suspend_traces = True
        try:
            bg_values = ["(없음)"] + tpl.list_assets("backgrounds")
            self.bg_combo.configure(values=bg_values)
            self.font_combo.configure(values=tpl.list_assets("fonts") or [""])

            if self._working_template is None:
                self.element_combo.configure(values=[""])
                self.element_combo.set("")
                self._bg_var.set("(없음)")
                self.preview_label.configure(image=None, text="(템플릿 없음)")
                return

            self._bg_var.set(self._working_template["background"] or "(없음)")

            element_labels = [f"{el['param']} ({el['type']})" for el in self._working_template["elements"]]
            self.element_combo.configure(values=element_labels)
            self.element_combo.set(element_labels[0])

            for el in self._working_template["elements"]:
                row = ctk.CTkFrame(self.template_params_frame, fg_color="transparent")
                row.pack(fill='x', pady=2)
                suffix = " *" if el["required"] else ""
                ctk.CTkLabel(
                    row, text=f"{el['param']}{suffix} ({el['type']})", width=130, anchor='w',
                    font=ctk.CTkFont(family="맑은 고딕", size=12)
                ).pack(side='left', padx=5)
                if el["type"] == "image":
                    path_var = tk.StringVar()
                    path_var.trace_add("write", lambda *_: self._schedule_live_preview())
                    ctk.CTkButton(
                        row, text="파일 선택",
                        command=lambda v=path_var: self._pick_image_file(v),
                        font=ctk.CTkFont(family="맑은 고딕", size=11),
                        fg_color="gray25", hover_color="gray35", width=75, corner_radius=6
                    ).pack(side='left', padx=2)
                    ctk.CTkButton(
                        row, text="지우기",
                        command=lambda v=path_var: v.set(""),
                        font=ctk.CTkFont(family="맑은 고딕", size=11),
                        fg_color="gray25", hover_color="gray35", width=50, corner_radius=6
                    ).pack(side='left', padx=2)
                    ctk.CTkLabel(
                        row, textvariable=path_var, anchor='w',
                        font=ctk.CTkFont(family="맑은 고딕", size=11), text_color="gray"
                    ).pack(side='left', padx=5, fill='x', expand=True)
                    self._template_param_widgets[el["param"]] = {"type": "image", "path_var": path_var}
                else:
                    text_var = tk.StringVar()
                    text_var.trace_add("write", lambda *_: self._schedule_live_preview())
                    entry = ctk.CTkEntry(row, textvariable=text_var,
                                         font=ctk.CTkFont(family="맑은 고딕", size=12), width=200)
                    entry.pack(side='left', padx=2)
                    self._template_param_widgets[el["param"]] = {"type": el["type"], "widget": entry}
        finally:
            self._suspend_traces = False

        self._on_element_selected(self.element_combo.get())

    def _selected_element(self):
        """요소 콤보의 현재 선택에 해당하는 작업 사본 요소. 없으면 None."""
        if self._working_template is None:
            return None
        display = self.element_combo.get()
        for el in self._working_template["elements"]:
            if f"{el['param']} ({el['type']})" == display:
                return el
        return None

    def _on_element_selected(self, _display=None):
        """선택 요소의 값을 편집 필드에 반영."""
        el = self._selected_element()
        if el is None:
            return
        self._suspend_traces = True
        try:
            x, y, w, h = el["box_mm"]
            self._el_x_var.set(f"{x:g}"); self._el_y_var.set(f"{y:g}")
            self._el_w_var.set(f"{w:g}"); self._el_h_var.set(f"{h:g}")
            if el["type"] == "text":
                self.text_edit_frame.pack(fill='x', pady=2, after=self.text_edit_frame.master.winfo_children()[2])
                self._el_size_var.set(f"{el['size_pt']:g}")
                self._el_font_var.set(el["font"])
                self._el_align_var.set(el["align"])
                self._el_valign_var.set(el["valign"])
            else:
                self.text_edit_frame.pack_forget()
        finally:
            self._suspend_traces = False
        self._schedule_live_preview()

    def _on_edit_field_changed(self):
        if self._suspend_traces:
            return
        self._template_dirty = True
        self._schedule_live_preview()

    def _apply_fields_to_working(self):
        """편집 필드 값을 작업 사본에 반영. 잘못된 입력은 ValueError."""
        template = self._working_template
        if template is None:
            raise ValueError("템플릿이 선택되지 않았습니다")
        bg = self._bg_var.get()
        template["background"] = None if bg in ("", "(없음)") else bg
        el = self._selected_element()
        if el is not None:
            try:
                x = float(self._el_x_var.get()); y = float(self._el_y_var.get())
                w = float(self._el_w_var.get()); h = float(self._el_h_var.get())
            except ValueError:
                raise ValueError("위치 값은 숫자(mm)여야 합니다")
            if w <= 0 or h <= 0:
                raise ValueError("W/H는 양수여야 합니다")
            el["box_mm"] = [x, y, w, h]
            if el["type"] == "text":
                try:
                    size_pt = float(self._el_size_var.get())
                except ValueError:
                    raise ValueError("글자 크기는 숫자(pt)여야 합니다")
                if size_pt < 8:
                    raise ValueError("글자 크기는 8pt 이상이어야 합니다")
                el["size_pt"] = size_pt
                if self._el_font_var.get():
                    el["font"] = self._el_font_var.get()
                el["align"] = self._el_align_var.get() or el["align"]
                el["valign"] = self._el_valign_var.get() or el["valign"]
        return template

    def _save_layout(self):
        if self._working_template is None:
            messagebox.showwarning("경고", "템플릿을 선택해주세요.")
            return
        try:
            template = self._apply_fields_to_working()
            saved = tpl.save_template(template["id"], template)
        except ValueError as e:   # TemplateError 포함 (ValueError 상속)
            messagebox.showerror("저장 실패", str(e))
            return
        self._templates[saved["name"]] = saved
        self._working_template = copy.deepcopy(saved)
        self._template_dirty = False
        self._append_log(f"템플릿 레이아웃 저장됨: data/templates/{saved['id']}.json\n")
        self.preview_status.configure(text="저장됨", text_color="#4CAF50")
```

- [ ] **Step 5: 라이브 미리보기 메서드 추가**

```python
    def _schedule_live_preview(self):
        """디바운싱 — 연속 변경은 마지막 한 번만 렌더."""
        if self._live_after_id is not None:
            try:
                self.root.after_cancel(self._live_after_id)
            except Exception:
                pass
        self._live_after_id = self.root.after(LIVE_PREVIEW_DEBOUNCE_MS, self._update_live_preview)

    def _update_live_preview(self):
        self._live_after_id = None
        if self._working_template is None:
            return
        try:
            template = self._apply_fields_to_working()
        except ValueError as e:
            self.preview_status.configure(text=f"입력값 확인 필요: {e}", text_color="#FFB454")
            return   # 직전 미리보기 유지

        try:
            params = self._collect_template_params()
        except OSError as e:
            self.preview_status.configure(text=f"이미지 파일 오류: {e}", text_color="#FFB454")
            return
        # 필수 text 파라미터가 비어 있으면 샘플값으로 미리보기 (인쇄에는 적용 안 됨)
        for el in template["elements"]:
            if el["type"] == "text" and el["required"] and not params.get(el["param"]):
                params[el["param"]] = "홍길동"

        self._live_generation += 1
        gen = self._live_generation
        preview_tpl = {**copy.deepcopy(template), "dpi": LIVE_PREVIEW_DPI}
        guide_el = self._selected_element() if self._guide_var.get() else None
        guide_box = list(guide_el["box_mm"]) if guide_el else None

        def worker():
            try:
                img = compose.render(preview_tpl, params)
                if guide_box:
                    draw = ImageDraw.Draw(img)
                    x = tpl.mm_to_px(guide_box[0], LIVE_PREVIEW_DPI)
                    y = tpl.mm_to_px(guide_box[1], LIVE_PREVIEW_DPI)
                    w = tpl.mm_to_px(guide_box[2], LIVE_PREVIEW_DPI)
                    h = tpl.mm_to_px(guide_box[3], LIVE_PREVIEW_DPI)
                    draw.rectangle([x, y, x + w - 1, y + h - 1], outline=(220, 60, 60), width=1)
                error = None
            except tpl.TemplateParamError as e:
                img, error = None, str(e)
            except Exception as e:
                logger.warning("라이브 미리보기 렌더 실패: %s", e)
                img, error = None, f"렌더 오류: {e}"
            self.root.after(0, lambda: self._apply_live_preview(gen, img, error))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_live_preview(self, gen, img, error):
        if gen != self._live_generation:
            return   # 더 새로운 렌더가 예약/완료됨
        if error:
            self.preview_status.configure(text=f"입력값 확인 필요: {error}", text_color="#FFB454")
            return
        scale = min(PREVIEW_MAX_W / img.width, PREVIEW_MAX_H / img.height)
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        self._preview_ctk_image = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        self.preview_label.configure(image=self._preview_ctk_image, text="")
        self.preview_status.configure(
            text="실제 인쇄와 동일 렌더러 · 저해상도 표시", text_color="gray")
```

- [ ] **Step 6: 기존 메서드 정리**

- `_collect_template_params`: image 분기는 기존 유지 (text/qr 분기의 `spec["widget"].get()`은 그대로 동작 — textvariable을 붙였어도 `.get()` 동일)
- `_template_preview`(크게 보기)·`_template_test_print`·`_run_template_render`: **인쇄·크게 보기 전에 편집값을 반영**하도록 각 메서드 시작에서 `template = self._selected_template()` 대신:

```python
        if self._working_template is None:
            messagebox.showwarning("경고", "템플릿을 선택해주세요.")
            return
        try:
            template = copy.deepcopy(self._apply_fields_to_working())
        except ValueError as e:
            messagebox.showwarning("입력 오류", str(e))
            return
```

  (기존 `_selected_template` 메서드는 요소 콤보용 `_selected_element`와 혼동되므로 삭제하고 위 패턴으로 대체)
- `run(self)` 등 나머지 무변경

- [ ] **Step 7: 검증** — `python3 -m py_compile app/gui.py` + `python3 -m unittest discover -s tests` (43 green)
- [ ] **Step 8: Commit (src)** — `git add app/gui.py && git commit -m "feat: 템플릿 탭 레이아웃 편집기 — 요소 편집 필드·라이브 미리보기·가이드 박스·저장"`

---

### Task 3: 버전 2.7.0 + 문서

**Files:**
- Modify: `src/app/__init__.py` (VERSION="2.7.0"), `src/app/changelog.py`
- Modify: `CHANGELOG.md`, `docs/smoke-test.md` (외부)

- [ ] **Step 1: changelog.py 맨 앞:**

```python
    ("2.7.0", "2026-07-19", [
        "[추가] 템플릿 레이아웃 편집기 — 요소 위치(mm)·글자 크기·폰트·정렬을 GUI에서 조정",
        "[추가] 창 내장 라이브 미리보기 — 값 변경 시 즉시 갱신, 영역 가이드 박스 표시",
        "[추가] 레이아웃 저장 — data/templates/*.json에 반영되어 API에도 즉시 적용",
    ]),
```

- [ ] **Step 2: 외부 CHANGELOG.md v2.7.0 섹션 (같은 내용 요약), smoke-test.md 끝에:**

```markdown
## 템플릿 레이아웃 편집기 (v2.7.0)
- [ ] 감사장 선택 → 우측에 내장 미리보기 자동 표시
- [ ] 요소 콤보에서 name 선택 → X/Y/W/H·크기·폰트·정렬 값이 필드에 표시
- [ ] Y 값 수정 → 0.3초 내 미리보기에서 글자가 이동, 가이드 박스 함께 이동
- [ ] 가이드 표시 체크 해제 → 빨간 박스 사라짐
- [ ] X에 문자 입력 → 직전 미리보기 유지 + 주황 경고, 숫자 복원 시 정상 갱신
- [ ] [레이아웃 저장] → data/templates/감사장.json 갱신, 브라우저 /preview-template에도 반영
- [ ] 미저장 상태에서 템플릿 변경/새로고침 → 확인 팝업
- [ ] 배경 콤보 변경 → 미리보기 배경 교체
- [ ] [크게 보기]·[테스트 인쇄]가 편집 중 값(저장 전)을 반영
- [ ] photo 파일 선택 → 미리보기에 사진 표시 (지우기로 제거)
```

- [ ] **Step 3: 검증(43 green)·커밋(src `chore: v2.7.0 버전·릴리스 노트`, 외부 `docs: v2.7.0 템플릿 편집기 문서 반영`+트레일러)·푸시**

---

## 자체 리뷰

- 스펙 커버리지: §1 2단 레이아웃(T2 S3), §2 라이브 미리보기·디바운스·세대 토큰·직전 유지·가이드(T2 S5), §3 작업 사본·저장·dirty 가드(T2 S4), §4 template.py 확장(T1), §5 검증·버전(T3). 스코프 외 항목 미구현 확인
- 타입 일관성: `save_template(id, data)`/`list_assets(kind)`/`load_template`의 `id` — T1 정의와 T2 사용 일치; `_apply_fields_to_working`이 ValueError를 던지고 `TemplateError ⊂ ValueError`라 `_save_layout`의 단일 except로 처리됨; `_selected_template` 삭제와 대체 패턴 명시
- 플레이스홀더 없음
