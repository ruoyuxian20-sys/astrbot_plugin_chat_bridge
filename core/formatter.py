"""转发消息格式化与清洗。"""
from __future__ import annotations

import re

CQ_RE = re.compile(r"\[CQ:[^\]]*\]")


def sanitize_text(text: str) -> str:
    """去掉 CQ 码与首尾空白。"""
    return CQ_RE.sub("", text).strip()


def build_forward_text(
    sender: str, content: str, show_sender: bool = True
) -> str:
    """构造转发文本：默认带发送者昵称前缀；无有效内容时返回空串。"""
    text = sanitize_text(content)
    if not text:
        return ""
    if not show_sender:
        return text
    name = (sender or "群友").strip()
    return f"{name}：{text}"
