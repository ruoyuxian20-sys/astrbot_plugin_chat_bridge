"""核心逻辑测试：不依赖 AstrBot 运行时。"""
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from chat_bridge.core import formatter, forward, policy, storage

# ---------- formatter ----------


def test_formatter_basic():
    assert formatter.build_forward_text("小明", "晚上好") == "小明：晚上好"
    assert formatter.build_forward_text("小明", "晚上好", show_sender=False) == "晚上好"
    assert formatter.build_forward_text("", "   ", True) == ""
    assert (
        formatter.build_forward_text("小明", "[CQ:image,file=x] 看看图", True)
        == "小明：看看图"
    )


def test_formatter_empty_sender():
    assert formatter.build_forward_text("", "你好") == "群友：你好"


# ---------- storage ----------


def test_storage_register_and_bind():
    state = storage.empty_state()
    storage.register_target(state, "主群", "aiocqhttp:GroupMessage:1", now=1.0)
    assert storage.add_binding(state, "aiocqhttp:GroupMessage:2", "主群") is True
    assert storage.add_binding(state, "aiocqhttp:GroupMessage:2", "不存在") is False
    assert storage.targets_for(state, "aiocqhttp:GroupMessage:2") == ["主群"]
    assert storage.targets_for(state, "aiocqhttp:GroupMessage:9") == []


def test_storage_one_source_many_targets():
    state = storage.empty_state()
    storage.register_target(state, "主群", "umo1", now=1.0)
    storage.register_target(state, "副群", "umo2", now=2.0)
    storage.add_binding(state, "source", "主群")
    storage.add_binding(state, "source", "副群")
    assert set(storage.targets_for(state, "source")) == {"主群", "副群"}
    assert storage.remove_binding(state, "source", "主群") is True
    assert storage.targets_for(state, "source") == ["副群"]
    assert storage.remove_binding(state, "source", "主群") is False


def test_storage_remove_target_cleans_bindings():
    state = storage.empty_state()
    storage.register_target(state, "主群", "umo1", now=1.0)
    storage.add_binding(state, "source", "主群")
    assert storage.remove_target(state, "主群") is True
    assert storage.targets_for(state, "source") == []
    assert storage.add_binding(state, "source", "主群") is False


def test_storage_roundtrip(tmp_path):
    path = str(tmp_path / "bridge.json")
    state = storage.empty_state()
    storage.register_target(state, "主群", "umo1")
    storage.add_binding(state, "umo2", "主群")
    storage.save_state(path, state)
    loaded = storage.load_state(path)
    assert loaded["targets"]["主群"]["umo"] == "umo1"
    assert storage.targets_for(loaded, "umo2") == ["主群"]


def test_storage_load_corrupt(tmp_path):
    path = tmp_path / "bridge.json"
    path.write_text("{not json", encoding="utf-8")
    assert storage.load_state(str(path)) == storage.empty_state()


# ---------- policy ----------


def test_policy_admin():
    assert policy.is_admin_sender("1", True, [])
    assert policy.is_admin_sender("2", False, ["2", "3"])
    assert not policy.is_admin_sender("4", False, ["2", "3"])


# ---------- forward ----------


def test_forward_build_nodes_payload():
    messages = [
        {
            "user_id": 10001,
            "nickname": "小明",
            "message": [{"type": "text", "data": {"text": "你好"}}],
        },
        {
            "sender": {"user_id": 10002, "nickname": "小红"},
            "message": [{"type": "image", "data": {"url": "https://x/y.png"}}],
        },
        {"user_id": 10003, "nickname": "空消息", "message": []},
        "not-a-dict",
    ]
    nodes = forward.build_nodes_payload(messages)
    assert len(nodes) == 2
    assert nodes[0]["data"]["uin"] == "10001"
    assert nodes[0]["data"]["name"] == "小明"
    assert nodes[1]["data"]["uin"] == "10002"
    assert nodes[1]["data"]["name"] == "小红"
    assert nodes[1]["data"]["content"][0]["type"] == "image"


def test_forward_extract_group_id():
    assert forward.extract_group_id("aiocqhttp:GroupMessage:group_123456") == "123456"
    assert forward.extract_group_id("aiocqhttp:GroupMessage:123456") == "123456"
    assert forward.extract_group_id("telegram_1:GroupMessage:88888") == "88888"
    assert forward.extract_group_id("aiocqhttp:GroupMessage:group_abc") is None
    assert forward.extract_group_id("") is None
    assert forward.extract_group_id("aiocqhttp:PrivateMessage:123456") is None


def test_forward_unwrap_action_data():
    assert forward.unwrap_action_data({"data": {"messages": [1]}}) == {"messages": [1]}
    assert forward.unwrap_action_data({"messages": [1]}) == {"messages": [1]}
    assert forward.unwrap_action_data(None) == {}
    assert forward.unwrap_action_data("x") == {}
