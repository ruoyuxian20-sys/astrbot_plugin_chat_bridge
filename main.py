"""群聊转发插件：把指定群聊的消息转发到另一群聊。"""
from __future__ import annotations

import os

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

try:
    from astrbot.api.message import MessageChain
except ImportError:
    from astrbot.api.event import MessageChain

from .core import formatter, forward, policy, storage, umo

_HELP_TEXT = """🔁 群聊转发使用说明

在【目标群】执行（仅管理员）：
/转发 注册目标 [备注名]
    把当前会话登记为转发目标，例如 /转发 注册目标 主群

在【源群】执行（仅管理员）：
/转发 绑定 <备注名>
    把当前群的消息转发到该目标，例如 /转发 绑定 主群
/转发 解绑 <备注名>
    停止转发到该目标

按群号配置（仅管理员，无需进入对应群）：
/转发 群目标 <备注名> <目标群号>
    按群号登记转发目标，例如 /转发 群目标 主群 123456
/转发 群绑定 <备注名> <源群号>
    按群号绑定源群，例如 /转发 群绑定 主群 654321

管理：
/转发 列表
    查看目标与绑定关系（仅管理员）
/转发 清空
    清空所有绑定与目标（仅管理员）
/转发 帮助
    查看本说明

说明：转发内容保持原样，不添加任何前缀或占位；支持文本、
图片与合并转发（聊天记录）；机器人自己的消息不会被再次转发。"""


class ChatBridge(Star):
    """群聊转发：源群消息实时推送到绑定的目标群。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._state_data: dict | None = None
        self._dirty = False

    # ---------- 工具 ----------

    def _cfg(self, key: str, default):
        try:
            return self.config.get(key, default)
        except Exception:
            return default

    def _state_path(self) -> str:
        try:
            base = getattr(self.context, "data_dir", None) or "data"
        except Exception:
            base = "data"
        return os.path.join(base, "plugins", "chat_bridge", "bridge.json")

    def _state(self) -> dict:
        if self._state_data is None:
            self._state_data = storage.load_state(self._state_path())
        return self._state_data

    def _save(self) -> None:
        if not self._dirty:
            return
        try:
            storage.save_state(self._state_path(), self._state())
            self._dirty = False
        except Exception as e:
            logger.warning(f"chat_bridge 保存规则失败: {e}")

    def _text(self, event: AstrMessageEvent) -> str:
        try:
            return event.get_message_str() or ""
        except Exception:
            try:
                return event.message_str or ""
            except Exception:
                return ""

    def _remainder(self, event: AstrMessageEvent) -> str:
        parts = self._text(event).strip().split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    def _sender_id(self, event: AstrMessageEvent) -> str:
        try:
            return str(event.get_sender_id() or "")
        except Exception:
            return ""

    def _sender_name(self, event: AstrMessageEvent) -> str:
        try:
            return (event.get_sender_name() or "").strip()
        except Exception:
            return ""

    def _is_bot(self, event: AstrMessageEvent) -> bool:
        """判断消息是否由机器人自己发出（防止转发回环）。"""
        sid = self._sender_id(event)
        if not sid:
            return False
        try:
            self_id = event.get_self_id()
            if self_id and sid == str(self_id):
                return True
        except Exception:
            pass
        try:
            self_id = getattr(event.message_obj, "self_id", "")
            if self_id and sid == str(self_id):
                return True
        except Exception:
            pass
        return False

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        platform_admin = False
        try:
            platform_admin = bool(event.is_admin())
        except Exception:
            pass
        if not platform_admin:
            try:
                get_role = getattr(event, "get_role", None)
                if callable(get_role):
                    platform_admin = str(get_role()) == "admin"
            except Exception:
                pass
        return policy.is_admin_sender(
            self._sender_id(event),
            platform_admin,
            list(self._cfg("admin_ids", [])),
        )

    def _onebot_call_action(self, event: AstrMessageEvent):
        """获取 OneBot v11 平台的通用 action 调用器（用于合并转发）。"""
        try:
            bot = getattr(event, "bot", None)
            api = getattr(bot, "api", None)
            call_action = getattr(api, "call_action", None)
            return call_action if callable(call_action) else None
        except Exception:
            return None

    # ---------- 命令 ----------

    @filter.command("forward", alias={"转发", "zhuanfa"})
    async def forward_cmd(self, event: AstrMessageEvent):
        """群聊转发：/转发 注册目标｜绑定｜解绑｜列表｜清空｜帮助"""
        remainder = self._remainder(event)
        if not remainder:
            yield event.plain_result(_HELP_TEXT)
            return
        parts = remainder.split(maxsplit=1)
        sub = parts[0].strip("，,。.")
        rest = parts[1].strip() if len(parts) > 1 else ""
        if sub in {"帮助", "help", "菜单", "usage"}:
            yield event.plain_result(_HELP_TEXT)
        elif sub in {"注册目标", "目标", "reg"}:
            async for result in self._reg(event, rest):
                yield result
        elif sub in {"绑定", "桥接", "bind"}:
            async for result in self._bind(event, rest):
                yield result
        elif sub in {"群目标", "目标群", "grouptarget"}:
            async for result in self._reg_group(event, rest):
                yield result
        elif sub in {"群绑定", "绑定群", "groupbind"}:
            async for result in self._bind_group(event, rest):
                yield result
        elif sub in {"解绑", "unbind"}:
            async for result in self._unbind(event, rest):
                yield result
        elif sub in {"列表", "list", "名单"}:
            async for result in self._list(event):
                yield result
        elif sub in {"清空", "clear"}:
            async for result in self._clear(event):
                yield result
        else:
            yield event.plain_result(f"未知子命令：{sub}\n\n{_HELP_TEXT}")

    async def _reg(self, event: AstrMessageEvent, rest: str):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可以登记转发目标。")
            return
        umo = event.unified_msg_origin
        label = rest.split(maxsplit=1)[0] if rest.strip() else ""
        if not label:
            label = f"目标{len(self._state().get('targets', {})) + 1}"
        state = self._state()
        previous = state["targets"].get(label)
        storage.register_target(state, label, umo)
        self._dirty = True
        self._save()
        if previous and previous.get("umo") == umo:
            yield event.plain_result(f"目标「{label}」已更新为当前会话。")
        else:
            yield event.plain_result(f"已把当前会话登记为转发目标「{label}」。")

    async def _bind(self, event: AstrMessageEvent, rest: str):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可以配置转发规则。")
            return
        label = rest.split(maxsplit=1)[0] if rest.strip() else ""
        if not label:
            yield event.plain_result("用法：/转发 绑定 <备注名>")
            return
        state = self._state()
        if label not in state["targets"]:
            yield event.plain_result(
                f"没有找到目标「{label}」，请先在目标群执行 /转发 注册目标 {label}"
            )
            return
        source = event.unified_msg_origin
        if source == state["targets"][label]["umo"]:
            yield event.plain_result("不能把群聊转发给它自己。")
            return
        storage.add_binding(state, source, label)
        self._dirty = True
        self._save()
        yield event.plain_result(f"已绑定：当前群 → 「{label}」。")

    async def _reg_group(self, event: AstrMessageEvent, rest: str):
        """按群号登记转发目标（无需进入目标群）。"""
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可以登记转发目标。")
            return
        parts = rest.split()
        if len(parts) < 2:
            yield event.plain_result("用法：/转发 群目标 <备注名> <目标群号>")
            return
        label, group_id = parts[0], parts[1]
        target_umo = umo.group_umo_from_example(
            event.unified_msg_origin, group_id
        )
        if not target_umo:
            yield event.plain_result("群号格式不正确（应为数字）。")
            return
        state = self._state()
        previous = state["targets"].get(label)
        storage.register_target(state, label, target_umo)
        self._dirty = True
        self._save()
        if previous and previous.get("umo") == target_umo:
            yield event.plain_result(f"目标「{label}」已更新为群 {group_id}。")
        else:
            yield event.plain_result(
                f"已按群号登记目标「{label}」→ 群 {group_id}（{target_umo}）。"
            )

    async def _bind_group(self, event: AstrMessageEvent, rest: str):
        """按群号绑定源群（无需进入源群）。"""
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可以配置转发规则。")
            return
        parts = rest.split()
        if len(parts) < 2:
            yield event.plain_result("用法：/转发 群绑定 <备注名> <源群号>")
            return
        label, group_id = parts[0], parts[1]
        state = self._state()
        if label not in state["targets"]:
            yield event.plain_result(
                f"没有找到目标「{label}」，请先登记目标（/转发 群目标 {label} <群号>）"
            )
            return
        source_umo = umo.group_umo_from_example(
            event.unified_msg_origin, group_id
        )
        if not source_umo:
            yield event.plain_result("群号格式不正确（应为数字）。")
            return
        if source_umo == state["targets"][label]["umo"]:
            yield event.plain_result("不能把群聊转发给它自己。")
            return
        storage.add_binding(state, source_umo, label)
        self._dirty = True
        self._save()
        yield event.plain_result(
            f"已按群号绑定：群 {group_id}（{source_umo}）→ 「{label}」。"
        )

    async def _unbind(self, event: AstrMessageEvent, rest: str):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可以配置转发规则。")
            return
        label = rest.split(maxsplit=1)[0] if rest.strip() else ""
        if not label:
            yield event.plain_result("用法：/转发 解绑 <备注名>")
            return
        removed = storage.remove_binding(
            self._state(), event.unified_msg_origin, label
        )
        if removed:
            self._dirty = True
            self._save()
            yield event.plain_result(f"已解绑：当前群 → 「{label}」。")
        else:
            yield event.plain_result(f"当前群没有绑定到「{label}」。")

    async def _list(self, event: AstrMessageEvent):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可以查看转发规则。")
            return
        state = self._state()
        lines = ["🔁 转发规则："]
        targets = storage.list_targets(state)
        if not targets:
            lines.append("（还没有登记任何目标）")
        for row in targets:
            lines.append(f"目标「{row['label']}」 → {row['umo']}")
        bindings = storage.list_bindings(state)
        if not bindings:
            lines.append("（还没有任何绑定）")
        for row in bindings:
            lines.append(f"源 {row['source_umo']} → 「{row['label']}」")
        yield event.plain_result("\n".join(lines))

    async def _clear(self, event: AstrMessageEvent):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可以清空转发规则。")
            return
        state = self._state()
        state["targets"] = {}
        state["sources"] = {}
        self._dirty = True
        self._save()
        yield event.plain_result("已清空所有转发目标与绑定。")

    # ---------- 转发 ----------

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """群消息钩子：命中绑定规则时转发到目标群。"""
        if self._is_bot(event):
            return
        text = self._text(event).strip()
        if not text or text.startswith(("/", "／")):
            return
        labels = storage.targets_for(self._state(), event.unified_msg_origin)
        if not labels:
            return
        await self._forward(event, labels)

    async def _forward(
        self, event: AstrMessageEvent, labels: list[str]
    ) -> None:
        content = self._text(event)
        text = formatter.build_forward_text(
            self._sender_name(event),
            content,
            bool(self._cfg("show_sender", False)),
        )
        merged = self._merged_segments(event)
        merged_present = bool(merged) and bool(self._cfg("forward_merged", True))
        targets = self._state().get("targets", {})
        for label in labels:
            umo = targets.get(label, {}).get("umo", "")
            if not umo:
                continue
            if merged_present:
                try:
                    ok = await self._send_merged(event, umo, merged)
                except Exception as e:
                    logger.warning(f"chat_bridge 合并转发到 {label} 失败: {e}")
                    ok = False
                if ok:
                    continue
                # 无法原样转发合并记录：源消息若有纯文本则原样转发，否则静默跳过
                if text:
                    try:
                        await self._send(event, umo, self._plain_chain(text))
                    except Exception as e:
                        logger.warning(f"chat_bridge 转发到 {label} 失败: {e}")
                else:
                    logger.warning(f"chat_bridge 合并转发到 {label} 无法转发，已跳过")
                continue
            chain = self._build_chain(text, event)
            if chain is None:
                continue
            try:
                await self._send(event, umo, chain)
            except Exception as e:
                logger.warning(f"chat_bridge 转发到 {label} 失败: {e}")

    def _merged_segments(self, event: AstrMessageEvent) -> list:
        """提取消息链中的合并转发相关段（Forward / Node / Nodes）。"""
        try:
            segments = event.message_obj.message or []
        except Exception:
            return []
        return [
            seg for seg in segments if isinstance(seg, (Comp.Forward, Comp.Node, Comp.Nodes))
        ]

    async def _send_merged(
        self, event: AstrMessageEvent, umo: str, segments: list
    ) -> bool:
        """以合并转发记录形式发送：优先拉取原记录重建，透传兜底。"""
        inline: list = []
        for seg in segments:
            if isinstance(seg, Comp.Nodes):
                inline.extend(seg.nodes or [])
            elif isinstance(seg, Comp.Node):
                inline.append(seg)
        fwd_ids = [
            str(getattr(seg, "id", "") or "")
            for seg in segments
            if isinstance(seg, Comp.Forward)
        ]
        call_action = self._onebot_call_action(event)
        gid = forward.extract_group_id(umo)
        nodes: list = []
        if call_action:
            if inline:
                for node in inline:
                    try:
                        nodes.append(node.toDict())
                    except Exception:
                        continue
            elif fwd_ids and fwd_ids[0]:
                try:
                    ret = await call_action(
                        "get_forward_msg", message_id=fwd_ids[0]
                    )
                    data = forward.unwrap_action_data(ret)
                    messages = (
                        data.get("messages", []) if isinstance(data, dict) else []
                    )
                    nodes = forward.build_nodes_payload(messages)
                except Exception as e:
                    logger.warning(f"chat_bridge 获取合并转发内容失败: {e}")
        if nodes and call_action and gid:
            try:
                await call_action(
                    "send_forward_msg",
                    group_id=int(gid) if gid.isdigit() else gid,
                    messages=nodes,
                )
                return True
            except Exception as e:
                logger.warning(f"chat_bridge send_forward_msg 失败: {e}")
        # 透传兜底：直接带 forward id / 内联节点发送（部分 OneBot 实现支持）
        if fwd_ids:
            for fid in fwd_ids:
                if not fid:
                    continue
                try:
                    await self.context.send_message(
                        umo, MessageChain([Comp.Forward(id=fid)])
                    )
                    return True
                except Exception:
                    continue
        if inline:
            try:
                await self.context.send_message(
                    umo, MessageChain([Comp.Nodes(nodes=inline)])
                )
                return True
            except Exception:
                pass
        return False

    def _build_chain(self, text: str, event: AstrMessageEvent):
        """构造转发消息链：文本 + 图片（尽力转发，失败占位）。"""
        parts = []
        if text:
            parts.append(Comp.Plain(text))
        if self._cfg("forward_images", True):
            try:
                segments = event.message_obj.message or []
            except Exception:
                segments = []
            for seg in segments:
                try:
                    if str(getattr(seg, "type", "")).lower() != "image":
                        continue
                    parts.extend(self._image_components(seg))
                except Exception as e:
                    logger.debug(f"chat_bridge 图片段处理跳过: {e}")
                    continue
        if not parts:
            return None
        try:
            return MessageChain(parts)
        except TypeError:
            chain = MessageChain()
            for part in parts:
                chain.append(part)
            return chain

    def _image_components(self, seg) -> list:
        """把收到的图片段转成可发送的图片组件（多策略兜底）。"""
        url = str(getattr(seg, "url", "") or "")
        file = str(getattr(seg, "file", "") or "")
        path = str(getattr(seg, "path", "") or "")
        candidates = []
        for candidate in (url, file):
            if candidate.startswith(("http://", "https://")):
                candidates.append(Comp.Image.fromURL(candidate))
        for local in (path, file):
            if local and os.path.exists(local):
                candidates.append(Comp.Image.fromFileSystem(local))
        if candidates:
            return candidates
        # 无法重建时，原样带上收到的图片段，交由适配器处理
        logger.debug(
            f"chat_bridge 图片段无可用 url/file，尝试原样转发: {seg}"
        )
        return [seg]

    def _plain_chain(self, text: str):
        """纯文本消息链。"""
        return MessageChain([Comp.Plain(text)]) if text else None

    async def _send(
        self, event: AstrMessageEvent, umo: str, chain
    ) -> None:
        """跨会话发送；兼容新旧版本 send_message 签名。"""
        try:
            await self.context.send_message(umo, chain)
        except TypeError:
            platform = str(umo).split(":", 1)[0]
            await self.context.send_message(platform, umo, chain)

    async def terminate(self):
        self._save()
        logger.info("chat_bridge 插件已停止")
