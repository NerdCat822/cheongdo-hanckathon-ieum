#!/usr/bin/env bash
# 소개자료 PDF(docs/ieum-intro.pdf)를 index.html에서 다시 만든다.
# 필요: Chrome 또는 Chromium 헤드리스, 나눔 글꼴(NanumSquare, NanumBarunGothic).
set -euo pipefail
cd "$(dirname "$0")"
BROWSER="${CHROME_BIN:-$(command -v google-chrome || command -v chromium || command -v chromium-browser)}"
OUT="$(cd .. && pwd)/ieum-intro.pdf"
"$BROWSER" --headless=new --disable-gpu --no-sandbox --no-pdf-header-footer \
  --virtual-time-budget=3000 --print-to-pdf="$OUT" "file://$(pwd)/index.html" 2>/dev/null
echo "written: $OUT"
