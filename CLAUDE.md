# CLAUDE.md

@AGENTS.md

- Vòng làm việc: `/trangthai <tên>` → `/the <mã-thẻ>` → (test trước, code) → `/kiemtra` → `/xong <mã-thẻ>` → `/pr`. Bug: `/sualoi <số>`.
- Trước khi commit gọi subagent `kiem-kien-truc` rà diff. Tra tài liệu thư viện bằng context7, không đoán API.
- Hướng dẫn đầy đủ (plugin, prompt mẫu, lỗi thường gặp): `docs/vibe-coding.md`.
- Trả lời và viết comment bằng tiếng Việt; tên biến, hàm, commit prefix theo mã thẻ.
- Trên Windows dùng Git Bash hoặc PowerShell đều được; script Python ghi UTF-8.
