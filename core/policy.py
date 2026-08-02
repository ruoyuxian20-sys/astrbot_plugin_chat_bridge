"""权限判定（纯函数）。"""
from __future__ import annotations


def is_admin_sender(
    sender_id: str, platform_admin: bool, admin_ids: list[str]
) -> bool:
    """管理员判定：平台管理员优先，配置的 admin_ids 兜底。"""
    if platform_admin:
        return True
    if sender_id and admin_ids:
        allowed = {str(a) for a in admin_ids}
        if sender_id in allowed:
            return True
    return False
