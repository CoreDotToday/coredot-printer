# 탭 UI 재구성 + 템플릿 탭 (v2.6.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GUI를 [서버]/[키오스크]/[템플릿] 탭으로 재구성하고, 템플릿 탭에서 서버 비경유 미리보기·테스트 인쇄를 제공한다 (v2.6.0).

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-19-tab-ui-template-tab-design.md`. `setup_ui()`를 공통 영역 + 탭 빌더 3개로 분해. 기존 위젯 블록은 **부모 컨테이너 변수만 바꿔 이동**(위젯 속성·바인딩·로직 메서드 무변경). 템플릿 탭은 `compose.render()`/`jobs.submit()` 직접 호출(HTTP 비경유), 렌더는 데몬 스레드 + `root.after` 반영.

**Tech Stack:** customtkinter CTkTabview, tkinter.filedialog. API·모의 서버 변경 없음.

**환경:** WSL — gui.py는 `py_compile`만 가능, 기존 unittest 36개 green 유지. 실동작은 Windows 스모크.
커밋: src 중첩 repo(한 줄·트레일러 없음), 문서는 외부 repo(트레일러 포함).

---

### Task 1: setup_ui 탭 재구성 (기존 위젯 이동)

**Files:**
- Modify: `src/app/gui.py`

- [ ] **Step 1: import 보강** — gui.py 상단에 추가:

```python
import subprocess
import tempfile
from tkinter import filedialog
```

(`from tkinter import messagebox`는 기존 유지. `from . import compose`를 `from . import autostart, kiosk` 다음 줄에 추가 — Windows 전용 모듈이므로 PIL import 무관하게 배치.)

- [ ] **Step 2: `setup_ui()` 골격 교체**

현재 `setup_ui()`의 구조(위에서 아래): status_frame → info_frame(주소+버전+포트 입력) → printer_frame(프린터+자동실행+외부접속) → kiosk_frame → button_frame → log_frame → bottom_frame → `self.update_log()`.

새 골격 (기존 위젯 생성 코드 블록은 삭제하지 말고 각 빌더 메서드로 **이동**):

```python
    def setup_ui(self):
        # ── 상태 표시줄 (공통) ── 기존 status_frame 블록 그대로
        # ── 서버 주소 정보줄 (공통) ── 기존 info_frame에서 포트 라벨/엔트리/저장 버튼을 제외한
        #     '서버 주소:' 라벨 + url_label + version_inline 만 유지 (포트는 [서버] 탭으로 이동)
        # ── 탭 ──
        self.tabview = ctk.CTkTabview(self.root, height=380)
        self.tabview.pack(fill='x', padx=10, pady=(0, 4))
        self._build_server_tab(self.tabview.add("서버"))
        self._build_kiosk_tab(self.tabview.add("키오스크"))
        self._build_template_tab(self.tabview.add("템플릿"))
        # ── 제어 버튼 (공통) ── 기존 button_frame 블록 그대로
        # ── 서버 로그 (공통) ── 기존 log_frame 블록 그대로
        # ── 하단 정보줄 (공통) ── 기존 bottom_frame 블록 그대로
        self.update_log()
```

- [ ] **Step 3: `_build_server_tab(self, parent)` 작성**

포트 설정 행(신규 배치, 위젯은 기존 것 이동):

```python
    def _build_server_tab(self, parent):
        port_frame = ctk.CTkFrame(parent, fg_color="transparent")
        port_frame.pack(fill='x', padx=10, pady=(8, 0))
        ctk.CTkLabel(port_frame, text="포트:", font=ctk.CTkFont(family="맑은 고딕", size=12)).pack(side='left', padx=5)
        # 기존 info_frame에 있던 self.port_entry 생성 코드와 '저장' 버튼 코드를 이곳으로 이동
        # (부모를 port_frame으로 변경, 그 외 속성 동일)
```

이어서 기존 printer_frame 블록 전체(콤보·새로고침·상태 라벨·안내문·auto_start_frame·allow_external 체크박스 포함)를 이동 — `create_labeled_frame(self.root, "프린터 설정")` → `create_labeled_frame(parent, "프린터 설정")`. 내부 코드는 무변경.

- [ ] **Step 4: `_build_kiosk_tab(self, parent)` 작성** — 기존 kiosk_frame 블록 전체 이동
  (`create_labeled_frame(self.root, "키오스크 설정")` → `parent`). 내부 무변경.

- [ ] **Step 5: 검증** — `python3 -m py_compile app/gui.py` +
  `grep -c "def _build_" app/gui.py` → 3. 남은 참조 확인: `grep -n "info_frame" app/gui.py`에서
  포트 위젯이 info_frame을 부모로 갖지 않아야 함.
  (Task 2의 `_build_template_tab`이 아직 없으므로 Step 5는 Task 2 후 함께 검증해도 됨 —
  이 경우 Task 1+2를 한 커밋으로 묶지 말고 임시로 `def _build_template_tab(self, parent): pass`를 두고 커밋)

- [ ] **Step 6: Commit (src)** — `git add app/gui.py && git commit -m "refactor: GUI를 서버/키오스크/템플릿 탭으로 재구성 (위젯 이동, 로직 무변경)"`

---

### Task 2: 템플릿 탭 구현

**Files:**
- Modify: `src/app/gui.py` (`_build_template_tab` 본문 + 신규 메서드들)

- [ ] **Step 1: `__init__`에 상태 변수 추가** (키오스크 변수 블록 아래):

```python
        # 템플릿 탭 상태
        self._templates = {}              # name → 정규화된 템플릿
        self._template_param_widgets = {} # param → {"type", "widget"|"path_var"}
        self._template_busy = False       # 렌더 중 재진입 방지
```

- [ ] **Step 2: `_build_template_tab` 본문**

```python
    def _build_template_tab(self, parent):
        select_row = ctk.CTkFrame(parent, fg_color="transparent")
        select_row.pack(fill='x', padx=10, pady=(8, 4))
        ctk.CTkLabel(select_row, text="템플릿:", font=ctk.CTkFont(family="맑은 고딕", size=12)).pack(side='left', padx=5)
        self.template_combo = ctk.CTkComboBox(
            select_row, state='readonly', width=220,
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

        # 파라미터 입력 영역 (템플릿 선택 시 동적 생성)
        self.template_params_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.template_params_frame.pack(fill='x', padx=10, pady=4)

        action_row = ctk.CTkFrame(parent, fg_color="transparent")
        action_row.pack(fill='x', padx=10, pady=4)
        self.template_preview_button = ctk.CTkButton(
            action_row, text="미리보기", command=self._template_preview,
            font=ctk.CTkFont(family="맑은 고딕", size=12, weight="bold"),
            fg_color="#2196F3", hover_color="#42A5F5", width=110, corner_radius=6
        )
        self.template_preview_button.pack(side='left', padx=5)
        self.template_print_button = ctk.CTkButton(
            action_row, text="테스트 인쇄", command=self._template_test_print,
            font=ctk.CTkFont(family="맑은 고딕", size=12, weight="bold"),
            fg_color="#4CAF50", hover_color="#66BB6A", width=110, corner_radius=6
        )
        self.template_print_button.pack(side='left', padx=5)

        folder_row = ctk.CTkFrame(parent, fg_color="transparent")
        folder_row.pack(fill='x', padx=10, pady=(4, 8))
        for label, kind in (("템플릿 폴더", "templates"), ("배경 폴더", "backgrounds"), ("폰트 폴더", "fonts")):
            ctk.CTkButton(
                folder_row, text=label,
                command=lambda k=kind: self._open_data_folder(k),
                font=ctk.CTkFont(family="맑은 고딕", size=11),
                fg_color="gray25", hover_color="gray35", width=90, corner_radius=6
            ).pack(side='left', padx=4)

        self._refresh_templates()
```

- [ ] **Step 3: 신규 메서드들** (`_open_kiosk_chrome` 아래에 추가)

```python
    # ── 템플릿 탭 ──────────────────────────────────

    def _refresh_templates(self):
        """템플릿 목록을 백그라운드에서 로드해 콤보 갱신."""
        def worker():
            try:
                templates = {t["name"]: t for t in tpl.list_templates()}
            except Exception as e:
                logger.warning("템플릿 목록 로드 실패: %s", e)
                templates = {}
            self.root.after(0, lambda: self._apply_templates(templates))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_templates(self, templates):
        self._templates = templates
        names = list(templates)
        current = self.template_combo.get()
        self.template_combo.configure(values=names or ["(템플릿 없음)"])
        if names:
            selected = current if current in names else names[0]
            self.template_combo.set(selected)
            self._on_template_selected(selected)
        else:
            self.template_combo.set("(템플릿 없음)")
            self._on_template_selected(None)

    def _on_template_selected(self, name):
        """파라미터 입력 행을 템플릿 스키마에 맞춰 재생성."""
        for child in self.template_params_frame.winfo_children():
            child.destroy()
        self._template_param_widgets = {}
        template = self._templates.get(name) if name else None
        if template is None:
            return
        for el in template["elements"]:
            row = ctk.CTkFrame(self.template_params_frame, fg_color="transparent")
            row.pack(fill='x', pady=2)
            suffix = " *" if el["required"] else ""
            ctk.CTkLabel(
                row, text=f"{el['param']}{suffix} ({el['type']})", width=140, anchor='w',
                font=ctk.CTkFont(family="맑은 고딕", size=12)
            ).pack(side='left', padx=5)
            if el["type"] == "image":
                path_var = tk.StringVar()
                ctk.CTkButton(
                    row, text="파일 선택",
                    command=lambda v=path_var: self._pick_image_file(v),
                    font=ctk.CTkFont(family="맑은 고딕", size=11),
                    fg_color="gray25", hover_color="gray35", width=80, corner_radius=6
                ).pack(side='left', padx=2)
                ctk.CTkLabel(
                    row, textvariable=path_var, anchor='w',
                    font=ctk.CTkFont(family="맑은 고딕", size=11), text_color="gray"
                ).pack(side='left', padx=5, fill='x', expand=True)
                self._template_param_widgets[el["param"]] = {"type": "image", "path_var": path_var}
            else:
                entry = ctk.CTkEntry(row, font=ctk.CTkFont(family="맑은 고딕", size=12), width=260)
                entry.pack(side='left', padx=2)
                self._template_param_widgets[el["param"]] = {"type": el["type"], "widget": entry}

    def _pick_image_file(self, path_var):
        path = filedialog.askopenfilename(
            title="이미지 선택",
            filetypes=[("이미지", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("모든 파일", "*.*")]
        )
        if path:
            path_var.set(path)

    def _selected_template(self):
        name = self.template_combo.get()
        template = self._templates.get(name)
        if template is None:
            messagebox.showwarning("경고", "템플릿을 선택해주세요.")
        return template

    def _collect_template_params(self):
        """입력 위젯에서 파라미터 dict 구성. 이미지 파일은 bytes로 읽는다."""
        params = {}
        for param, spec in self._template_param_widgets.items():
            if spec["type"] == "image":
                path = spec["path_var"].get().strip()
                if path:
                    with open(path, "rb") as f:
                        params[param] = f.read()
            else:
                value = spec["widget"].get().strip()
                if value:
                    params[param] = value
        return params

    def _run_template_render(self, template, on_done):
        """백그라운드 렌더 공통부. on_done(image or None, error or None)는 GUI 스레드에서 호출."""
        if self._template_busy:
            return
        self._template_busy = True
        self.template_preview_button.configure(state='disabled')
        self.template_print_button.configure(state='disabled')
        try:
            params = self._collect_template_params()
        except OSError as e:
            self._template_render_done()
            messagebox.showerror("오류", f"이미지 파일을 읽을 수 없습니다.\n{e}")
            return

        def worker():
            try:
                image = compose.render(template, params)
                error = None
            except tpl.TemplateParamError as e:
                image, error = None, str(e)
            except Exception as e:
                logger.warning("조판 실패: %s", e)
                image, error = None, f"조판 중 오류가 발생했습니다: {e}"
            self.root.after(0, lambda: (self._template_render_done(), on_done(image, error)))

        threading.Thread(target=worker, daemon=True).start()

    def _template_render_done(self):
        self._template_busy = False
        self.template_preview_button.configure(state='normal')
        self.template_print_button.configure(state='normal')

    def _template_preview(self):
        template = self._selected_template()
        if template is None:
            return
        preview_template = {**template, "dpi": 150}

        def on_done(image, error):
            if error:
                messagebox.showwarning("미리보기 실패", error)
                return
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            image.save(path, "PNG")
            self._append_log(f"미리보기 생성: {template['name']} → {path}\n")
            self._open_path(path)

        self._run_template_render(preview_template, on_done)

    def _template_test_print(self):
        template = self._selected_template()
        if template is None:
            return
        printer = self.selected_printer.get()
        if not printer:
            messagebox.showwarning("경고", "먼저 [서버] 탭에서 프린터를 선택해주세요.")
            return
        if not messagebox.askyesno("테스트 인쇄", f"'{template['name']}' 템플릿을 '{printer}'로 인쇄할까요?"):
            return

        def on_done(image, error):
            if error:
                messagebox.showwarning("인쇄 실패", error)
                return
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            image.save(path, "PNG", dpi=(template["dpi"], template["dpi"]))
            job_id = jobs.submit(path, printer, filename=f"{template['name']}.png")
            self._append_log(f"테스트 인쇄 제출: {template['name']} → {printer} (job {job_id[:8]})\n")

        self._run_template_render(template, on_done)

    def _open_data_folder(self, kind):
        path = os.path.join(tpl.data_dir(), kind)
        try:
            os.makedirs(path, exist_ok=True)
            self._open_path(path)
        except OSError as e:
            messagebox.showerror("오류", f"폴더를 열 수 없습니다.\n{e}")

    def _open_path(self, path):
        """OS 기본 앱으로 파일/폴더 열기 (Windows 우선, 실패는 로그만)."""
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)   # noqa: Windows 전용
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            logger.warning("열기 실패 (%s): %s", path, e)
            self._append_log(f"열기 실패: {path} ({e})\n")
```

주의: `_run_template_render`의 `worker`에서 `on_done`이 GUI 스레드(`root.after`)에서 실행되도록 유지할 것. `jobs.submit`에 넘긴 임시 PNG는 큐가 삭제하므로 GUI가 지우지 않는다. 미리보기 PNG는 OS 뷰어가 여는 동안 유지돼야 하므로 삭제하지 않는다(임시 폴더에 남음 — 허용).

- [ ] **Step 4: 검증**

```bash
python3 -m py_compile app/gui.py
python3 -m unittest discover -s tests    # 36 green
grep -c "def _template\|def _refresh_templates\|def _apply_templates\|def _on_template_selected\|def _open_data_folder\|def _open_path\|def _pick_image_file\|def _collect_template_params\|def _selected_template\|def _run_template_render" app/gui.py   # 11
```

- [ ] **Step 5: Commit (src)** — `git add app/gui.py && git commit -m "feat: 템플릿 탭 — 목록·파라미터 폼·미리보기·테스트 인쇄·폴더 열기 (서버 비경유)"`

---

### Task 3: 버전 2.6.0 + 문서

**Files:**
- Modify: `src/app/__init__.py`, `src/app/changelog.py`
- Modify: `CHANGELOG.md`, `docs/smoke-test.md` (외부 repo)

- [ ] **Step 1: VERSION = "2.6.0"; changelog.py 맨 앞에:**

```python
    ("2.6.0", "2026-07-19", [
        "[변경] GUI를 [서버]/[키오스크]/[템플릿] 탭으로 재구성 — 조판 미사용 현장은 템플릿 탭만 무시하면 됨",
        "[추가] 템플릿 탭: 템플릿 선택·파라미터 입력·미리보기·테스트 인쇄·폴더 열기",
        "[개선] 미리보기·테스트 인쇄는 서버 미기동 상태에서도 동작 (좌표 조정 작업 간소화)",
    ]),
```

- [ ] **Step 2: 외부 CHANGELOG.md 맨 위에 동일 취지의 v2.6.0 섹션:**

```markdown
## v2.6.0 (2026-07-19)

- GUI를 [서버]/[키오스크]/[템플릿] 탭으로 재구성
- 템플릿 탭 추가: 템플릿 선택·파라미터 입력·미리보기·테스트 인쇄·data 폴더 열기
- 미리보기·테스트 인쇄는 서버를 시작하지 않아도 동작
```

- [ ] **Step 3: docs/smoke-test.md 맨 끝에 추가:**

```markdown
## 탭 UI · 템플릿 탭 (v2.6.0)
- [ ] 탭 3개([서버]/[키오스크]/[템플릿]) 전환 시 각 설정 값 유지, 상태줄·제어버튼·로그는 항상 표시
- [ ] [서버] 탭에서 포트 저장·프린터 선택·자동 실행·외부 접속이 기존과 동일 동작 (회귀)
- [ ] [키오스크] 탭 URL 저장/삭제/자동 열기/확대율 동작 (회귀)
- [ ] [템플릿] 탭: 감사장 선택 → photo(image)/name(text*) 입력 행 생성
- [ ] 서버 **중지 상태**에서 name 입력 후 [미리보기] → OS 이미지 뷰어로 조판 결과 표시
- [ ] name 비우고 [미리보기] → "필수 파라미터가 없습니다: name" 경고
- [ ] [테스트 인쇄] → 확인 팝업 → 인쇄물 = 미리보기 일치, 로그에 job id
- [ ] 폴더 열기 3버튼 → 탐색기로 data/templates·backgrounds·fonts 열림
- [ ] 렌더 중 버튼 비활성화 → 완료 후 복원
```

- [ ] **Step 4: 검증·커밋·푸시** — src unittest 36 green →
  src: `git add app/__init__.py app/changelog.py && git commit -m "chore: v2.6.0 버전·릴리스 노트"`;
  외부: `git add CHANGELOG.md docs/smoke-test.md && git commit -m "docs: v2.6.0 탭 UI·템플릿 탭 문서 반영"(트레일러 포함) && git push origin main`

---

## 자체 리뷰

- 스펙 커버리지: 창 구조·공통 영역(T1), 템플릿 탭 6요소 전부(T2 — 목록/동적 폼/미리보기/테스트 인쇄/폴더/서버 비경유·스레드·재진입 방지), 버전·스모크(T3). API 무변경 → mock 미수정 확인
- 타입 일관성: `tpl.list_templates()/data_dir()`, `compose.render(template, params)`, `jobs.submit(path, printer, filename)`, `TemplateParamError` — 기존 시그니처와 일치. `_template_param_widgets` 구조를 생성(_on_template_selected)과 소비(_collect_template_params)가 동일 키로 사용
- 플레이스홀더 없음
