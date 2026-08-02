"""转发消息格式化与清洗。"""
from __future__ import annotations

import re

CQ_RE = re.compile(r"\[CQ:[^\]]*\]")
# AstrBot 对非文本消息段的占位符，如 [图片] / [转发消息] / [At:123] / [表情:1] / [引用消息(...)]
PLACEHOLDER_RE = re.compile(
    r"\[(?:图片|转发消息|表情:[^\]]*|At:[^\]]*|引用消息[^\]]*)\]"
)


def sanitize_text(text: str) -> str:
    """去掉 CQ 码、平台占位符与首尾空白。"""
    text = CQ_RE.sub("", text)
    text = PLACEHOLDER_RE.sub("", text)
    return text.strip()


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
