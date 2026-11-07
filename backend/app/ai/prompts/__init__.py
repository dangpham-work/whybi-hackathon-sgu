"""PromptRegistry tối giản (Phụ lục A): prompt nằm trong `<tên>.md` cạnh file này, có số phiên bản ở dòng
chú thích đầu. Biến `{tên}` được điền lúc chạy bằng thay chuỗi, không dùng str.format, để JSON mẫu
có ngoặc nhọn trong prompt không bị hiểu là biến. Chủ: Đăng.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any


def format_transcript(transcript: str | list[dict[str, Any]]) -> str:
    """Lượt hội thoại thành văn bản có nhãn, dùng chung cho các tác tử."""
    if isinstance(transcript, str):
        return transcript
    labels = {"student": "SV", "tutee": "AI học trò"}
    return "\n".join(
        f"[{labels.get(str(turn.get('role', 'student')).lower(), 'SV')}] {turn.get('text', '')}" for turn in transcript
    )


_DIR = Path(__file__).resolve().parent
_COMMENT = re.compile(r"<!--.*?-->\s*", re.S)
_VAR = re.compile(r"\{([a-z_]+)\}")


@lru_cache
def load_prompt(name: str) -> str:
    return _COMMENT.sub("", (_DIR / f"{name}.md").read_text(encoding="utf-8")).strip()


def prompt_version(name: str) -> str:
    m = re.search(r"phiên bản:\s*([^\s·>-]+)", (_DIR / f"{name}.md").read_text(encoding="utf-8"))
    return m.group(1) if m else "v0"


def render_prompt(name: str, **values: str) -> str:
    """Điền mọi biến `{x}` (chữ thường, gạch dưới). Thiếu biến ⇒ KeyError để lỗi lộ ngay khi test."""
    text = load_prompt(name)
    missing = sorted({v for v in _VAR.findall(text) if v not in values})
    if missing:
        raise KeyError(f"prompt {name} thiếu biến: {', '.join(missing)}")
    return _VAR.sub(lambda m: str(values[m.group(1)]), text)


def wrap_student_text(text: str, tag: str = "student_transcript") -> str:
    """Nội dung SV luôn là DỮ LIỆU: bọc trong thẻ và vô hiệu thẻ đóng / mở do SV tự chèn."""
    safe = re.sub(rf"</?\s*{tag}\s*>", lambda m: m.group(0).replace("<", "‹").replace(">", "›"), text, flags=re.I)
    return f"<{tag}>{safe}</{tag}>"
