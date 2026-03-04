# Nuitka 빌드 전환 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** PyInstaller를 Nuitka로 교체하여 백신에 차단되지 않는 단일 exe를 빌드한다.

**Architecture:** `build_release.py`를 Nuitka 커맨드로 전면 교체. `printer_server.py`의 PyInstaller 전용 코드(`sys._MEIPASS`, `sys.frozen`)를 Nuitka 호환으로 수정. `requirements.txt`에 nuitka 추가.

**Tech Stack:** Nuitka, Python, Visual Studio Build Tools (C 컴파일러)

---

### Task 1: requirements.txt에 nuitka 추가

**Files:**
- Modify: `src/requirements.txt`

**Step 1: 의존성 추가**

`src/requirements.txt` 끝에 추가:
```
nuitka
ordered-set
```

**Step 2: Commit**

```bash
git add src/requirements.txt
git commit -m "build: add nuitka and ordered-set to requirements"
```

---

### Task 2: printer_server.py의 PyInstaller 전용 코드 제거

**Files:**
- Modify: `src/printer_server.py:11-25` (show_startup_error 함수)
- Modify: `src/printer_server.py:225-235` (아이콘 경로 탐색)

**Step 1: show_startup_error의 frozen 감지 수정**

`src/printer_server.py` 의 `show_startup_error` 함수에서:

변경 전:
```python
        log_path = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                                else os.path.dirname(os.path.abspath(__file__)), "error.log")
```

변경 후:
```python
        log_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "error.log")
```

**Step 2: 아이콘 경로 탐색을 Nuitka 호환으로 수정**

`PrinterAPILauncher.__init__` 의 아이콘 설정 부분:

변경 전:
```python
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base_path, 'printer.ico')
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass
```

변경 후:
```python
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base_path, 'printer.ico')
            if not os.path.exists(icon_path):
                # onefile 모드: exe와 같은 디렉토리에서도 탐색
                icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'printer.ico')
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass
```

**Step 3: printer_server.py를 소스 모드로 실행하여 동작 확인**

Run: `cd src && python printer_server.py`
Expected: GUI가 정상적으로 뜨고 아이콘이 표시됨

**Step 4: Commit**

```bash
git add src/printer_server.py
git commit -m "refactor: replace PyInstaller-specific code with Nuitka-compatible paths"
```

---

### Task 3: build_release.py를 Nuitka용으로 교체

**Files:**
- Modify: `src/build_release.py` (전면 재작성)

**Step 1: build_release.py 전체 교체**

```python
# -*- coding: utf-8 -*-
"""
프린터 서버 Release 버전 빌드 스크립트
Nuitka를 사용하여 단일 실행 파일(.exe) 생성
Python 설치 없이 어떤 Windows에서든 실행 가능
"""
import subprocess
import sys
import os
import shutil


def check_nuitka():
    """Nuitka 설치 확인 및 자동 설치"""
    try:
        import nuitka
        print("[OK] Nuitka가 이미 설치되어 있습니다.")
        return True
    except ImportError:
        print("Nuitka가 설치되어 있지 않습니다.")
        print("Nuitka를 설치합니다...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "nuitka", "ordered-set"])
        print("[OK] Nuitka 설치 완료")
        return True


def build_exe():
    """실행 파일 빌드"""
    print("\n" + "=" * 60)
    print("프린터 서버 Release 빌드 시작 (Nuitka 단일 파일 버전)")
    print("=" * 60 + "\n")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print(f"작업 디렉토리: {script_dir}\n")

    if not check_nuitka():
        print("[ERROR] Nuitka 설치 실패")
        return False

    # 아이콘 파일 확인
    icon_file = "printer.ico"
    has_icon = os.path.exists(icon_file)
    if not has_icon:
        print(f"[경고] {icon_file} 파일이 없습니다. 기본 아이콘을 사용합니다.")

    # Nuitka 빌드 명령어 구성
    cmd = [
        sys.executable, "-m", "nuitka",
        "--mode=onefile",
        "--windows-console-mode=disable",
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
        "--include-module=psutil",
        # tkinter 플러그인
        "--enable-plugin=tk-inter",
        # 빌드 캐시 사용 (재빌드 시 빠름)
        "--remove-output",
    ]

    # 아이콘 추가
    if has_icon:
        cmd.append(f"--windows-icon-from-ico={icon_file}")
        cmd.append(f"--include-data-file={icon_file}={icon_file}")
        print(f"[OK] 아이콘: {icon_file}")

    # 메인 스크립트
    cmd.append("printer_server.py")

    print("\n빌드 명령어:")
    print(" ".join(cmd[:8]) + " ... (옵션 생략)")
    print("\n빌드 중... (첫 빌드는 수 분 소요될 수 있습니다)\n")

    try:
        result = subprocess.run(cmd, check=True)

        if result.returncode == 0:
            print("\n" + "=" * 60)
            print("[SUCCESS] 빌드 성공!")
            print("=" * 60)

            exe_path = os.path.join(script_dir, "dist", "프린터서버.exe")

            if os.path.exists(exe_path):
                size_mb = os.path.getsize(exe_path) / 1024 / 1024
                print(f"\n실행 파일 위치: {exe_path}")
                print(f"파일 크기: {size_mb:.2f} MB")

                # Release 폴더 생성
                release_dir = os.path.join(script_dir, "release")
                os.makedirs(release_dir, exist_ok=True)

                release_exe = os.path.join(release_dir, "프린터서버.exe")
                shutil.copy2(exe_path, release_exe)
                print(f"\n[OK] Release 폴더에 복사됨: {release_exe}")

                readme_path = os.path.join(release_dir, "README.txt")
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write("프린터 서버 - 단일 실행 파일 버전\n")
                    f.write("=" * 50 + "\n\n")
                    f.write("특징:\n")
                    f.write("- Python 설치 불필요\n")
                    f.write("- 단일 exe 파일로 실행\n")
                    f.write("- 어떤 Windows PC에서든 실행 가능\n\n")
                    f.write("실행 방법:\n")
                    f.write("1. '프린터서버.exe'를 더블클릭하여 실행\n")
                    f.write("2. GUI에서 프린터 선택\n")
                    f.write("3. '시작' 버튼 클릭\n\n")
                    f.write("서버 정보:\n")
                    f.write("- 포트: 8000\n")
                    f.write("- 주소: http://localhost:8000\n\n")
                    f.write("API 엔드포인트:\n")
                    f.write("- GET  /printers     : 프린터 목록 조회\n")
                    f.write("- POST /print-image  : 이미지 인쇄 (printer 파라미터 선택)\n")
                    f.write("- GET  /health       : 서버 상태 확인\n")
                print("[OK] README.txt 생성됨")

                print("\n" + "=" * 60)
                print(f"Release 폴더: {release_dir}")
                print("=" * 60)
                print("\n[INFO] 배포 준비 완료!")
                print("프린터서버.exe 파일 하나만 배포하면 됩니다.\n")

            return True
        else:
            print("[ERROR] 빌드 실패")
            return False

    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] 빌드 중 오류 발생: {e}")
        return False
    except Exception as e:
        print(f"\n[ERROR] 예상치 못한 오류: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("    프린터 서버 Release 빌드 도구 (Nuitka)")
    print("=" * 60)

    success = build_exe()

    if success:
        print("\n[SUCCESS] 모든 작업이 완료되었습니다!")
        print("\n사용 방법:")
        print("1. release 폴더로 이동")
        print("2. '프린터서버.exe' 더블클릭 (Python 설치 불필요)")
    else:
        print("\n[ERROR] 빌드 실패")
        sys.exit(1)

    input("\n\n계속하려면 Enter를 누르세요...")
```

**Step 2: Commit**

```bash
git add src/build_release.py
git commit -m "build: replace PyInstaller with Nuitka for antivirus-friendly builds"
```

---

### Task 4: 빌드 테스트

**Step 1: Nuitka 및 의존성 설치**

Run: `cd src && pip install -r requirements.txt`
Expected: nuitka, ordered-set 포함 전체 설치 성공

**Step 2: 빌드 실행**

Run: `cd src && python build_release.py`
Expected: `src/dist/프린터서버.exe` 생성, `src/release/` 에 복사됨

> 참고: 첫 빌드 시 Nuitka가 Visual Studio Build Tools(C 컴파일러)가 없으면 자동 설치를 안내합니다. 안내에 따라 설치 후 재실행하세요.

**Step 3: exe 실행 테스트**

Run: `src\release\프린터서버.exe` (Windows에서 더블클릭)
Expected: GUI 정상 표시, 프린터 목록 로드, 서버 시작/중지 동작

**Step 4: Commit**

```bash
git add -A
git commit -m "build: verify Nuitka build works"
```
