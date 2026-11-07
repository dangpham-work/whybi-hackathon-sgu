"""Hook PostToolUse: tự chạy ruff (sửa lỗi an toàn + format) cho file .py trong backend/ vừa được AI sửa.

Không bao giờ chặn phiên làm việc: lỗi gì cũng chỉ in cảnh báo rồi thoát 0.
"""

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    path = Path((data.get("tool_input") or {}).get("file_path") or "")
    root = Path(data.get("cwd") or ".")
    backend = next((p / "backend" for p in (root, *root.parents) if (p / "backend" / "pyproject.toml").exists()), None)
    if path.suffix != ".py" or backend is None or backend.resolve() not in path.resolve().parents:
        return
    for args in (["check", "--fix", "--quiet"], ["format", "--quiet"]):
        try:
            subprocess.run(["uv", "run", "ruff", *args, str(path)], cwd=backend, timeout=25, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"[format hook] bỏ qua ruff: {exc}", file=sys.stderr)
            return


if __name__ == "__main__":
    main()
