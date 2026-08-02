"""转发规则持久化（JSON，本地存储）。"""
from __future__ import annotations

import json
import os
import time


def empty_state() -> dict:
    return {"targets": {}, "sources": {}, "updated_at": 0.0}


def _now() -> float:
    return time.time()


def load_state(path: str) -> dict:
    """读取规则文件；不存在或损坏时返回空结构。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            return empty_state()
        if not isinstance(state.get("targets"), dict):
            state["targets"] = {}
        if not isinstance(state.get("sources"), dict):
            state["sources"] = {}
        return state
    except (OSError, ValueError):
        return empty_state()


def save_state(path: str, state: dict) -> None:
    """原子写入：先写临时文件再替换。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    state["updated_at"] = _now()
    tmp_path = os.path.join(directory, f".{os.path.basename(path)}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp_path, path)


def register_target(
    state: dict, label: str, umo: str, now: float | None = None
) -> None:
    """登记一个转发目标会话（按备注名）。"""
    state.setdefault("targets", {})[label] = {
        "umo": umo,
        "created_at": now if now is not None else _now(),
    }


def remove_target(state: dict, label: str) -> bool:
    """删除目标，并把它从所有源群的绑定中移除。"""
    targets = state.get("targets", {})
    if label not in targets:
        return False
    del targets[label]
    for labels in state.get("sources", {}).values():
        if label in labels:
            labels.remove(label)
    return True


def add_binding(state: dict, source_umo: str, label: str) -> bool:
    """绑定 源会话 -> 目标；目标不存在时返回 False。"""
    if label not in state.get("targets", {}):
        return False
    sources = state.setdefault("sources", {})
    labels = sources.setdefault(source_umo, [])
    if label not in labels:
        labels.append(label)
    return True


def remove_binding(state: dict, source_umo: str, label: str) -> bool:
    """解除 源会话 -> 目标 的绑定。"""
    sources = state.get("sources", {})
    labels = sources.get(source_umo, [])
    if label not in labels:
        return False
    labels.remove(label)
    if not labels:
        del sources[source_umo]
    return True


def targets_for(state: dict, source_umo: str) -> list[str]:
    """返回该源会话绑定的目标备注名列表。"""
    return list(state.get("sources", {}).get(source_umo, []))


def list_targets(state: dict) -> list[dict]:
    """返回目标列表（含 UMO 与创建时间），按备注名排序。"""
    targets = state.get("targets", {})
    rows = []
    for label, info in sorted(targets.items()):
        rows.append(
            {
                "label": label,
                "umo": info.get("umo", ""),
                "created_at": info.get("created_at", 0.0),
            }
        )
    return rows


def list_bindings(state: dict) -> list[dict]:
    """返回所有绑定关系。"""
    sources = state.get("sources", {})
    rows = []
    for source_umo, labels in sorted(sources.items()):
        for label in labels:
            rows.append({"source_umo": source_umo, "label": label})
    return rows
