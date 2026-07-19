# Nuitka + customtkinter 트러블슈팅 가이드

> Nuitka onefile 빌드로 customtkinter 기반 Windows GUI 앱을 배포할 때 겪은 문제와 해결책을 정리한 문서입니다. Python → 단일 `.exe` 변환 과정에서 발생하는 주요 이슈를 다룹니다.

---

## 목차

1. [customtkinter 마이그레이션](#1-customtkinter-마이그레이션)
2. [Nuitka 빌드 설정](#2-nuitka-빌드-설정)
3. [콘솔 창 숨기기](#3-콘솔-창-숨기기)
4. [Python 버전 호환](#4-python-버전-호환)
5. [에러 처리](#5-에러-처리)
6. [크롬 키오스크](#6-크롬-키오스크)
7. [GUI 스레딩](#7-gui-스레딩)
8. [중복 실행 방지](#8-중복-실행-방지)

---

## 1. customtkinter 마이그레이션

### 위젯 매핑 테이블

| Tkinter | customtkinter | 비고 |
|---------|---------------|------|
| `tk.Tk()` | `ctk.CTk()` | |
| `tk.Frame()` | `ctk.CTkFrame()` | `bg=` → `fg_color=` |
| `tk.Label()` | `ctk.CTkLabel()` | `fg=` → `text_color=` |
| `tk.Button()` | `ctk.CTkButton()` | `bg=` → `fg_color=`, `relief` 제거, `corner_radius` 추가 |
| `tk.Checkbutton()` | `ctk.CTkCheckBox()` | |
| `tk.LabelFrame()` | CTkFrame + CTkLabel 조합 | 헬퍼 함수 필요 (아래 참고) |
| `ttk.Combobox(readonly)` | `ctk.CTkComboBox()` | 읽기 전용 드롭다운 |
| `ttk.Combobox(editable)` | `ctk.CTkEntry` + `ctk.CTkOptionMenu` | CTkComboBox는 직접 입력 미지원 |
| `scrolledtext.ScrolledText` | `ctk.CTkTextbox()` | `insert`, `see` 등 API 호환 |
| `tk.Toplevel()` | `ctk.CTkToplevel()` | 팝업 창 |
| `messagebox` | 그대로 사용 | customtkinter 대체제 없음 |
| `.config()` | `.configure()` | 메서드명 변경 |
| Font 튜플 | `ctk.CTkFont` 객체 | 예: `ctk.CTkFont(family="맑은 고딕", size=12, weight="bold")` |

### Import 변경

```python
# Before
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox

# After
import tkinter as tk
from tkinter import messagebox   # messagebox는 그대로
import customtkinter as ctk
```

### 테마 설정

```python
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

self.root = ctk.CTk()
```

### LabelFrame 대체 헬퍼

customtkinter에는 `LabelFrame`이 없으므로 직접 만들어야 합니다.

```python
def create_labeled_frame(parent, title):
    """LabelFrame 대체 헬퍼 — CTkFrame + 상단 타이틀 라벨"""
    frame = ctk.CTkFrame(parent, border_width=1, border_color="gray40")
    label = ctk.CTkLabel(
        frame, text=title,
        font=ctk.CTkFont(family="맑은 고딕", size=13, weight="bold")
    )
    label.pack(anchor='w', padx=10, pady=(8, 4))
    return frame
```

### 색상 컨벤션 (다크 테마)

| 용도 | 색상 |
|------|------|
| 시작 버튼 | `fg_color="#4CAF50"`, `hover_color="#66BB6A"` |
| 정지 버튼 | `fg_color="#f44336"`, `hover_color="#EF5350"` |
| 재시작 버튼 | `fg_color="#2196F3"`, `hover_color="#42A5F5"` |
| 새로고침 버튼 | `fg_color="#FFC107"`, `text_color="black"`, `hover_color="#FFD54F"` |
| 프레임 배경 | `fg_color="gray20"` |
| 프레임 테두리 | `border_color="gray40"` |
| 링크 텍스트 | `text_color="#5599FF"` |

---

## 2. Nuitka 빌드 설정

### 전체 빌드 명령

```python
cmd = [
    sys.executable, "-m", "nuitka",
    "--mode=onefile",                     # 단일 exe 생성
    "--windows-console-mode=disable",     # 콘솔 창 비활성화
    "--output-filename=프린터서버.exe",
    "--output-dir=dist",

    # 패키지 포함
    "--include-package=fastapi",
    "--include-package=starlette",
    "--include-package=uvicorn",
    "--include-package=pydantic",
    "--include-package=pydantic_core",
    "--include-package=annotated_types",
    "--include-package=PIL",
    "--include-package=anyio",
    "--include-package=sniffio",
    "--include-package=h11",
    "--include-package=click",
    "--include-package=python_multipart",
    "--include-module=win32print",
    "--include-module=win32ui",
    "--include-module=win32api",
    "--include-module=win32con",
    "--include-module=pywintypes",
    "--include-package=customtkinter",
    "--include-package-data=customtkinter",   # ⚠️ 필수!

    # tkinter 플러그인
    "--enable-plugin=tk-inter",

    # 빌드 후 중간 파일 정리
    "--remove-output",
]

# 아이콘
cmd.append(f"--windows-icon-from-ico={icon_file}")
cmd.append(f"--include-data-file={icon_file}={icon_file}")

# 메인 스크립트
cmd.append("printer_server.py")
```

### 핵심 주의사항: `--include-package-data`

```
--include-package=customtkinter        # Python 모듈만 포함
--include-package-data=customtkinter   # 테마 JSON, 이미지 등 데이터 파일 포함
```

`--include-package-data`를 빠뜨리면 빌드된 exe가 런타임에 테마 파일을 찾지 못해 크래시합니다. **반드시 둘 다** 지정해야 합니다.

### `--include-package` vs `--include-module`

- `--include-package=xxx` — 패키지 전체(하위 모듈 포함) 번들
- `--include-module=xxx` — 특정 모듈 하나만 번들
- pywin32 계열(`win32print`, `win32ui` 등)은 패키지 구조가 아니므로 `--include-module` 사용

### zig 컴파일러(`--zig`)를 쓰지 않는 이유

한때 빌드 속도를 위해 `--zig`를 사용했으나, **zig cc가 Windows 링킹 시 `.pdb` 파일을 함께 생성**하고
Nuitka(4.x)가 onefile 부트스트랩 링킹 중 예상 밖 `.pdb`를 발견하면 다음 FATAL로 빌드가 실패한다:

```
FATAL: Error, unwanted '.pdb' file '...\dist\_nuitka_temp.pdb' was created during the build. Report the bug.
```

`--zig`를 제거하면 MSVC(설치 시) 또는 MinGW64(최초 1회 자동 다운로드 후 캐시)가 사용되며 onefile과 완전 호환된다.
빌드 중 "Is it OK to download ... Proceed and download?" 프롬프트가 나오면 MinGW64 다운로드이므로 Yes로 진행하면 된다.

### Nuitka vs PyInstaller

Nuitka는 Python을 C로 컴파일하므로 PyInstaller 대비 안티바이러스 오탐이 적습니다. Windows Defender 등에서 차단되는 문제가 줄어듭니다.

---

## 3. 콘솔 창 숨기기

### 문제

Nuitka `--windows-console-mode=disable`만으로는 콘솔 창이 완전히 사라지지 않는 경우가 있습니다. 특히 소스 실행(`python printer_server.py`)이나 일부 환경에서 콘솔이 보입니다.

### 시도 1: `FreeConsole()` — 실패 ❌

```python
import ctypes
ctypes.windll.kernel32.FreeConsole()
sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')
```

**결과:** 소스 실행 시에는 동작하지만, **Nuitka onefile 빌드에서 크래시**합니다. `FreeConsole()`이 Nuitka onefile의 내부 파이프 핸들을 파괴하여 프로세스가 조용히 죽습니다. error.log도 생성되지 않습니다.

### 시도 2: `ShowWindow()` 단독 — 부분 성공 ⚠️

```python
import ctypes
hwnd = ctypes.windll.kernel32.GetConsoleWindow()
if hwnd:
    ctypes.windll.user32.ShowWindow(hwnd, 0)
```

**결과:** 콘솔 창은 숨겨지지만 **작업표시줄에 아이콘이 남아있습니다**.

### 최종 해결: `ShowWindow` + `WS_EX_TOOLWINDOW` — 성공 ✅

```python
# 콘솔 창 숨기기 + 작업표시줄 제거 (Nuitka onefile 호환)
try:
    import ctypes
    _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if _hwnd:
        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        style = ctypes.windll.user32.GetWindowLongW(_hwnd, GWL_EXSTYLE)
        style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
        ctypes.windll.user32.SetWindowLongW(_hwnd, GWL_EXSTYLE, style)
        ctypes.windll.user32.ShowWindow(_hwnd, 0)
except Exception:
    pass
```

**원리:**
- `WS_EX_APPWINDOW` 스타일 제거 → 작업표시줄에서 사라짐
- `WS_EX_TOOLWINDOW` 스타일 추가 → 도구 창 취급 (Alt+Tab에도 안 보임)
- `ShowWindow(hwnd, 0)` → 창 자체를 숨김

**핵심 교훈:** Nuitka onefile 빌드에서는 절대 `FreeConsole()`을 사용하면 안 됩니다. 내부 파이프 핸들이 파괴되어 프로세스가 조용히 죽습니다.

---

## 4. Python 버전 호환

### 문제

`requirements.txt`에서 `==`(정확한 버전)을 사용하면 Python 버전 업그레이드 시 빌드가 실패합니다.

```
# 문제가 되는 설정
pillow==10.1.0
fastapi==0.104.1
```

Python 3.13에서 Pillow 10.1.0을 빌드하면:

```
Collecting pillow==10.1.0
  Getting requirements to build wheel ... error
  KeyError: '__version__'
```

### 해결

`>=`(최소 버전)을 사용합니다.

```
# requirements.txt
fastapi>=0.104.1
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
pillow>=10.1.0
pywin32>=306
customtkinter
nuitka
ordered-set
```

빌드 도구(`nuitka`, `ordered-set`)와 자주 업데이트되는 라이브러리(`customtkinter`)는 버전을 고정하지 않아도 됩니다.

---

## 5. 에러 처리

### 원칙: 항상 파일에 기록 + 팝업 시도

Nuitka onefile 빌드에서는 콘솔이 없으므로 에러를 볼 수 없습니다. 항상 **파일에 먼저 기록**하고, 그 다음 팝업을 시도합니다.

```python
def show_startup_error(title, message):
    """시작 시 에러를 사용자에게 보여주는 함수 (GUI 초기화 전에도 동작)"""
    # 1. 항상 파일에 기록
    try:
        error_log = os.path.join(
            os.path.dirname(os.path.abspath(sys.argv[0])), "error.log"
        )
        with open(error_log, "w", encoding="utf-8") as f:
            f.write(f"{title}\n{message}\n")
    except Exception:
        pass
    # 2. 팝업 시도
    try:
        import tkinter as tk
        from tkinter import messagebox as mb
        root = tk.Tk()
        root.withdraw()
        mb.showerror(title, message)
        root.destroy()
    except Exception:
        pass
```

### import를 try/except로 감싸기

모든 import를 하나의 try 블록으로 묶으면, 빠진 모듈이 있을 때 사용자에게 명확한 에러를 보여줄 수 있습니다.

```python
try:
    import tkinter as tk
    from tkinter import messagebox
    import customtkinter as ctk
    from fastapi import FastAPI, File, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    # ... 기타 모듈 ...
except Exception as e:
    show_startup_error(
        "프린터 서버 시작 실패",
        f"필수 모듈을 로드할 수 없습니다.\n\n"
        f"오류: {type(e).__name__}: {e}\n\n"
        f"상세:\n{traceback.format_exc()}\n\n"
        f"이 오류가 계속되면 고객지원에 문의해주세요."
    )
    sys.exit(1)
```

### stderr를 파일로 리다이렉트

런타임 중 예상치 못한 에러도 캡처합니다.

```python
_error_log_path = os.path.join(
    os.path.dirname(os.path.abspath(sys.argv[0])), "error.log"
)
try:
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(_error_log_path, 'w', encoding='utf-8')
except:
    pass
```

---

## 6. 크롬 키오스크

### 문제

`--kiosk` 플래그로 Chrome을 실행해도 풀스크린이 아닌 일반 창으로 열립니다.

### 원인

Chrome이 이미 실행 중이면 `--kiosk` 등의 플래그가 무시됩니다. 기존 인스턴스에 URL만 전달되기 때문입니다.

### 해결: `--user-data-dir`로 독립 인스턴스

```python
def open_chrome_kiosk(url, zoom=100):
    """Chrome을 키오스크(풀스크린) 모드로 실행"""
    chrome = find_chrome()
    if not chrome:
        return False, "Chrome을 찾을 수 없습니다."
    try:
        # 별도 user data directory → 기존 Chrome과 독립적인 인스턴스
        kiosk_data_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", tempfile.gettempdir()),
            "CoreDotKiosk", "ChromeData"
        )
        scale_factor = zoom / 100.0
        subprocess.Popen([
            chrome,
            "--kiosk",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={kiosk_data_dir}",
            f"--force-device-scale-factor={scale_factor}",
            url,
        ])
        return True, None
    except Exception as e:
        return False, str(e)
```

### Chrome 경로 탐색

```python
def find_chrome():
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""),
                     "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""),
                     "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None
```

### 핵심 플래그

| 플래그 | 용도 |
|--------|------|
| `--kiosk` | 풀스크린 모드 |
| `--user-data-dir=...` | 독립 인스턴스 (기존 Chrome과 분리) |
| `--force-device-scale-factor=1.5` | 확대율 150% |
| `--no-first-run` | 첫 실행 안내 건너뛰기 |
| `--no-default-browser-check` | 기본 브라우저 확인 건너뛰기 |

---

## 7. GUI 스레딩

### 원칙: `time.sleep()` 금지, `root.after()` 사용

Tkinter/customtkinter의 메인 루프는 단일 스레드입니다. `time.sleep()`을 호출하면 **UI 전체가 멈춥니다**.

```python
# ❌ 잘못된 패턴 — UI가 1초간 프리징
def restart_server(self):
    self.stop_server()
    time.sleep(1)           # 메인 스레드 블로킹!
    self.start_server()

# ✅ 올바른 패턴 — 논블로킹
def restart_server(self):
    self.stop_server()
    self.root.after(1000, self.start_server)   # 1초 후 콜백
```

### Uvicorn을 데몬 스레드로 실행

```python
class UvicornServer:
    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        config = uvicorn.Config(api, host="0.0.0.0", port=8000,
                                log_level="info", access_log=True)
        self.server = uvicorn.Server(config)
        self._setup_log_redirect()
        self.server.run()

    def stop(self):
        if self.server and self.is_running:
            self.server.should_exit = True
            self.is_running = False
```

`daemon=True`로 설정하면 메인 스레드(GUI) 종료 시 서버도 자동 종료됩니다.

### 커스텀 로그 핸들러로 GUI에 로그 표시

Uvicorn 로그를 GUI의 텍스트박스에 표시하려면, logging 핸들러 → 큐 → GUI 폴링 패턴을 사용합니다.

**1단계: 커스텀 핸들러**

```python
class QueueLogHandler(logging.Handler):
    """logging 핸들러 — 로그를 큐 콜백으로 전달"""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        try:
            msg = self.format(record)
            self.callback(msg + "\n")
        except Exception:
            pass
```

**2단계: Uvicorn 로거에 핸들러 설정**

```python
def _setup_log_redirect(self):
    handler = QueueLogHandler(self.log_callback)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(message)s", datefmt="%H:%M:%S"
    ))
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
```

**3단계: GUI에서 큐 폴링**

```python
def update_log(self):
    """큐에서 로그를 가져와 UI 업데이트"""
    try:
        while True:
            line = self.log_queue.get_nowait()
            self.log_text.insert(tk.END, line)
            self.log_text.see(tk.END)
    except queue.Empty:
        pass
    self.root.after(100, self.update_log)   # 100ms마다 폴링
```

**흐름:** Uvicorn 워커 스레드 → `QueueLogHandler.emit()` → `queue.Queue` → `root.after(100ms)` → `CTkTextbox.insert()`

---

## 8. 중복 실행 방지

### 기존 방식: psutil 프로세스 이름 매칭 — 오탐 발생 ❌

```python
import psutil
current_pid = os.getpid()
for proc in psutil.process_iter(['pid', 'name']):
    try:
        if proc.info['pid'] != current_pid:
            if '프린터서버' in proc.info['name'].lower():
                messagebox.showwarning("경고", "이미 실행 중입니다.")
                sys.exit(0)
    except:
        pass
```

**문제:** 자기 자신의 cmdline에 `printer_server`가 포함되어 있거나, 이름이 유사한 다른 프로세스를 오탐합니다. 아무것도 실행 중이 아닌데 경고가 뜹니다.

**추가 문제:** psutil 의존성으로 빌드 크기가 증가합니다.

### 최종 방식: 포트 8000 소켓 체크 — 정확 ✅

```python
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _sock:
    _sock.settimeout(1)
    if _sock.connect_ex(('localhost', 8000)) == 0:
        messagebox.showwarning(
            "경고",
            "프린터 API 서버가 이미 실행 중입니다.\n(포트 8000 사용 중)"
        )
        sys.exit(0)
```

**장점:**
- 서버가 실제로 포트 8000에서 리스닝할 때만 탐지 → 오탐 없음
- `socket`은 표준 라이브러리 → 추가 의존성 없음
- psutil 제거 → Nuitka 빌드 시 `--include-module=psutil` 불필요 → exe 크기 감소

---

## 요약: 주요 에러와 해결책

| 에러 | 원인 | 해결 |
|------|------|------|
| `FATAL: failed to locate package 'customtkinter'` | pip 미설치 | `pip install customtkinter` |
| Pillow `KeyError: '__version__'` (Python 3.13) | `==` 버전 고정 | `>=`로 변경 |
| 빌드된 exe가 조용히 죽음 (error.log 없음) | `FreeConsole()` 파이프 파괴 | `ShowWindow` + `WS_EX_TOOLWINDOW`로 교체 |
| "이미 실행 중" 오탐 | psutil 프로세스명 부분 매칭 | 소켓 포트 체크로 교체 |
| Chrome `--kiosk` 무시됨 | 기존 Chrome 인스턴스 재사용 | `--user-data-dir`로 독립 인스턴스 |
| `time.sleep()` 중 UI 프리징 | 메인 스레드 블로킹 | `root.after(ms, callback)` |
| customtkinter 테마 파일 누락 크래시 | `--include-package-data` 누락 | 빌드 시 `--include-package-data=customtkinter` 추가 |
