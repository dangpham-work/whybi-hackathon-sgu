#!/usr/bin/env bash
# Tạo nhãn GitHub cho thẻ việc và bug (kế hoạch §8, Phụ lục C.1). Cần `gh auth login`. Chạy lại an toàn (--force).
set -euo pipefail
label() { gh label create "$1" --color "$2" --description "$3" --force; }

label card     "0B6E63" "Thẻ việc (docs/cards)"
label bug      "D73A4A" "Lỗi"
label P0       "B60205" "Hỏng bước demo hoặc sập deploy – dừng cả đội"
label P1       "D93F0B" "Lỗi rõ ràng – sửa trong 1–2 giờ"
label P2       "FBCA04" "Lỗi giao diện nhỏ"
for r in 1 2 3; do label "vong-$r" "C5DEF5" "Vòng $r"; done
for o in C1:dang C2:long GD:thang KT:quyen; do label "${o%%:*}" "F2A91B" "Thẻ của ${o##*:}"; done
for m in session voice documents skilltree mastery heatmap matching admin frontend infra eval; do
  label "mod:$m" "EDEDED" "Module $m"
done
