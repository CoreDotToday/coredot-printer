#!/usr/bin/env bash
# GitHub 릴리스 게시 스크립트 — WSL에서 실행 (gh CLI 인증 필요)
#
# 선행 조건: Windows에서 src/build_release.py 실행 완료
#            → src/release/CoreDotPrinter-<태그>.exe 생성됨
#
# 사용법:
#   scripts/publish_release.sh            # 릴리스 생성
#   scripts/publish_release.sh --dry-run  # 실행 없이 내용만 확인
set -euo pipefail

cd "$(dirname "$0")/.."

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# 버전은 src/app/__init__.py의 VERSION이 단일 출처
VERSION=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' src/app/__init__.py)
[[ -n "$VERSION" ]] || { echo "[ERROR] src/app/__init__.py에서 VERSION을 찾지 못했습니다."; exit 1; }
TAG=$(echo "$VERSION" | cut -d. -f1,2)   # 태그 관례: 2.4.0 → 2.4
ASSET="src/release/CoreDotPrinter-${TAG}.exe"
TITLE="프린터 서버"

echo "버전: $VERSION → 태그: $TAG"

[[ -f "$ASSET" ]] || {
    echo "[ERROR] 자산이 없습니다: $ASSET"
    echo "        Windows에서 'python build_release.py'를 먼저 실행하세요."
    exit 1
}

# 이미 게시된 태그면 중단 (버전 올리는 걸 잊은 경우 방지)
if gh release view "$TAG" >/dev/null 2>&1; then
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[WARN] 릴리스 $TAG 가 이미 존재합니다 (dry-run이라 계속 진행)."
    else
        echo "[ERROR] 릴리스 $TAG 가 이미 존재합니다."
        echo "        새 릴리스라면 src/app/__init__.py의 VERSION을 먼저 올리세요."
        exit 1
    fi
fi

# CHANGELOG.md에서 이 버전 섹션을 릴리스 노트로 추출
NOTES_FILE=$(mktemp)
trap 'rm -f "$NOTES_FILE"' EXIT
awk -v ver="## v${VERSION}" '
    index($0, ver) == 1 { found = 1 }
    found && /^## v/ && index($0, ver) != 1 { exit }
    found { print }
' CHANGELOG.md > "$NOTES_FILE"

[[ -s "$NOTES_FILE" ]] || {
    echo "[ERROR] CHANGELOG.md에서 'v${VERSION}' 섹션을 찾지 못했습니다. 변경 내역을 먼저 작성하세요."
    exit 1
}

echo "--- 릴리스 노트 (CHANGELOG.md v${VERSION} 섹션) ---"
cat "$NOTES_FILE"
echo "--------------------------------------------------"

# 미푸시 커밋이 있으면 푸시 (태그가 최신 main을 가리키도록)
git fetch origin main --quiet
if [[ -n "$(git log origin/main..main --oneline 2>/dev/null)" ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY-RUN] 미푸시 커밋 있음 → git push origin main 예정"
    else
        echo "[INFO] 미푸시 커밋을 푸시합니다..."
        git push origin main
    fi
fi

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[DRY-RUN] gh release create \"$TAG\" \"$ASSET\" --title \"$TITLE\" --notes-file <노트>"
else
    gh release create "$TAG" "$ASSET" --title "$TITLE" --notes-file "$NOTES_FILE"
    echo "[SUCCESS] 릴리스 $TAG 게시 완료"
fi
