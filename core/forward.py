"""合并转发记录的处理（纯 Python，可测试）。"""
from __future__ import annotations


def unwrap_action_data(ret: dict | None) -> dict:
    """OneBot action 返回解包：优先取 data 字段。"""
    if not isinstance(ret, dict):
        return {}
    data = ret.get("data")
    if isinstance(data, dict):
        return data
    return ret


def build_nodes_payload(messages: list) -> list[dict]:
    """把 get_forward_msg 的消息列表转成 send_forward_msg 的节点列表。

    每个节点保留发送者昵称/QQ 号与原始消息段，不做内容合并。
    """
    nodes: list[dict] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        sender = msg.get("sender") or {}
        user_id = msg.get("user_id") or sender.get("user_id") or 0
        nickname = msg.get("nickname") or sender.get("nickname") or ""
        content = msg.get("message") or msg.get("content") or []
        if not content:
            continue
        nodes.append(
            {
                "type": "node",
                "data": {
                    "uin": str(user_id),
                    "name": str(nickname),
                    "content": content,
                },
            }
        )
    return nodes


def extract_group_id(umo: str) -> str | None:
    """从目标会话 UMO 中提取群号。

    aiocqhttp 的群会话形如 ``aiocqhttp:GroupMessage:group_123456``。
    """
    try:
        parts = str(umo).split(":")
    except Exception:
        return None
    if len(parts) < 3:
        return None
    msg_type = parts[-2]
    if "group" not in msg_type.lower():
        return None
    session = parts[-1]
    for prefix in ("group_", "group-", "群"):
        if session.startswith(prefix):
            session = session[len(prefix) :]
            break
    if session.isdigit():
        return session
    return None
