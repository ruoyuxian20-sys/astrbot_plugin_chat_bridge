"""会话 UMO 构造（纯 Python，可测试）。"""
from __future__ import annotations

_GROUP_PREFIXES = ("group_", "group-", "群")


def group_umo_from_example(example_umo: str, group_id: str) -> str:
    """按群号构造群会话 UMO。

    平台与群会话前缀从 ``example_umo``（通常是当前事件的 UMO）推断：
    例如 ``aiocqhttp:GroupMessage:group_555`` → 平台 ``aiocqhttp``、前缀 ``group_``。
    """
    group_id = str(group_id).strip()
    if not group_id.isdigit():
        return ""
    parts = str(example_umo or "").split(":")
    platform = parts[0] if parts and parts[0] else "aiocqhttp"
    prefix = "group_"
    if len(parts) >= 3:
        session = parts[-1]
        for candidate in _GROUP_PREFIXES:
            if session.startswith(candidate):
                prefix = candidate
                break
    return f"{platform}:GroupMessage:{prefix}{group_id}"
