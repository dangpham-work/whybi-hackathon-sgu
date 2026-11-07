#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SLIDES_HTML="${ROOT_DIR}/docs/slides/slides.html"
SLIDES_PDF="${ROOT_DIR}/docs/slides/whybi-ai-presentation.pdf"

echo "Xuất slide Whybi AI sang PDF từ: ${SLIDES_HTML}"

CHROME_BIN=""
if command -v google-chrome &> /dev/null; then
  CHROME_BIN="google-chrome"
elif command -v chromium &> /dev/null; then
  CHROME_BIN="chromium"
elif command -v chromium-browser &> /dev/null; then
  CHROME_BIN="chromium-browser"
else
  echo "Lỗi: Không tìm thấy google-chrome hoặc chromium trên PATH." >&2
  exit 1
fi

"${CHROME_BIN}" --headless --disable-gpu --no-sandbox --print-to-pdf="${SLIDES_PDF}" "file://${SLIDES_HTML}"
echo "Đã xuất slide thành công: ${SLIDES_PDF}"
