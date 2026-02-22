"""Text export — formatted timeline export for sessions and games."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.session.timeline import get_game_timeline, get_timeline
from app.models.responses import _snapshot_display_name

EVENT_LABELS: dict[str, str] = {
    "session_start": "场景开始",
    "session_end": "场景结束",
    "game_start": "游戏开始",
    "game_end": "游戏结束",
    "player_join": "玩家加入",
    "player_leave": "玩家离开",
    "event_check": "事件判定",
    "reroll": "重投",
    "hard_reroll": "强制重投",
    "attack": "攻击",
    "defend": "防御",
    "comm_request": "通讯请求",
    "comm_accept": "通讯接受",
    "comm_reject": "通讯拒绝",
    "comm_cancel": "通讯取消",
    "apply_fragment": "色彩碎片",
    "hp_change": "HP变动",
    "region_transition": "区域转移",
    "location_transition": "地点转移",
    "item_use": "使用道具",
    "buff_add": "添加状态",
    "buff_remove": "移除状态",
    "item_grant": "发放道具",
    "event_define": "定义事件",
    "event_deactivate": "关闭事件",
    "attribute_set": "设定属性",
    "ability_add": "添加能力",
}


def _get_display_name(event) -> str:
    """Get display name from event's player_snapshot, falling back to actor_id."""
    snap = getattr(event, "player_snapshot", None)
    if snap is not None:
        return _snapshot_display_name(
            snap.username, snap.role, snap.patient_name, snap.ghost_name,
        )
    return event.actor_id or "系统"


def _collect_participants(events: list) -> list[str]:
    """Collect unique display names from events, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for e in events:
        name = _get_display_name(e)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _extract_content(event) -> str:
    """Extract human-readable content from event data based on event type."""
    data = json.loads(event.data_json) if event.data_json else {}
    result_data = json.loads(event.result_json) if event.result_json else {}
    et = event.event_type

    if event.narrative:
        return event.narrative

    if et == "event_check":
        success = "成功" if result_data.get("success") else "失败"
        pt = result_data.get("player_total", "?")
        tt = result_data.get("target_total", "?")
        return f"判定{success} (玩家:{pt} vs 目标:{tt})"

    if et in ("reroll", "hard_reroll"):
        label = "强制重投" if et == "hard_reroll" else "重投"
        success = "成功" if result_data.get("success") else "失败"
        pt = result_data.get("player_total", "?")
        tt = result_data.get("target_total", "?")
        return f"{label}{success} (玩家:{pt} vs 目标:{tt})"

    if et == "attack":
        hit = result_data.get("success", False)
        if hit:
            dmg = result_data.get("damage", "?")
            return f"命中！伤害:{dmg}"
        return "未命中"

    if et == "defend":
        success = result_data.get("success", False)
        val = result_data.get("total", "?")
        return f"防御{'成功' if success else '失败'} (防御值:{val})"

    if et == "comm_request":
        return f"向 {data.get('target_patient_id', '?')} 发起通讯"

    if et == "comm_accept":
        return "通讯已接受"

    if et == "hp_change":
        delta = data.get("delta", 0)
        new_hp = result_data.get("new_hp", "?")
        return f"HP{'+' if delta >= 0 else ''}{delta} → {new_hp}"

    if et == "apply_fragment":
        color = data.get("color", "?")
        value = data.get("value", "?")
        return f"获得{color.upper()}碎片 x{value}"

    if et == "region_transition":
        return f"移动至区域 {data.get('target_region_id', '?')}"

    if et == "location_transition":
        return f"移动至地点 {data.get('target_location_id', '?')}"

    if et == "buff_add":
        return f"添加状态「{data.get('name', '?')}」"

    if et == "buff_remove":
        return f"移除状态 {data.get('buff_id', '?')}"

    if et == "item_grant":
        return f"发放道具 x{data.get('count', 1)}"

    if et == "item_use":
        return f"使用道具 {data.get('item_def_id', '?')}"

    if et == "event_define":
        return f"定义事件「{data.get('name', '?')}」({data.get('expression', '?')})"

    if et == "event_deactivate":
        return f"关闭事件 {data.get('event_def_id', '?')}"

    if et == "attribute_set":
        return f"设定 {data.get('attribute', '?')} = {data.get('value', '?')}"

    if et == "ability_add":
        return f"添加能力「{data.get('name', '?')}」[{data.get('color', '?')}]"

    if et in ("session_start", "session_end", "game_start", "game_end"):
        return ""

    return ""


def _format_event_line(event) -> str:
    """Format a single timeline event into a text line."""
    ts = ""
    if event.created_at:
        ts = event.created_at.strftime("%H:%M")

    label = EVENT_LABELS.get(event.event_type, event.event_type)
    name = _get_display_name(event)
    content = _extract_content(event)

    line = f"[{ts}] [{label}] {name}"
    if content:
        line += f"\n{content}"
    return line


async def export_session_timeline(db: AsyncSession, session_id: str) -> str:
    """Export a session's timeline as formatted text."""
    events = await get_timeline(db, session_id, limit=9999)
    return _format_timeline(events)


async def export_game_timeline(db: AsyncSession, game_id: str) -> str:
    """Export a game's full timeline as formatted text."""
    events = await get_game_timeline(db, game_id, limit=9999)
    return _format_timeline(events)


def _format_timeline(events: list) -> str:
    """Build formatted text from a list of timeline events."""
    if not events:
        return "=== 灰山城系统自动生成（完整档案）===\n（无事件记录）\n"

    # Time range
    first_ts = events[0].created_at
    last_ts = events[-1].created_at
    time_start = first_ts.strftime("%Y-%m-%d %H:%M") if first_ts else "?"
    time_end = last_ts.strftime("%H:%M") if last_ts else "?"

    participants = _collect_participants(events)

    header_lines = [
        "=== 灰山城系统自动生成（完整档案）===",
        f"记录时段：{time_start} 至 {time_end}",
        f"参与信号：{', '.join(participants)}",
        f"总消息数：{len(events)}",
        "===================================",
        "",
    ]

    body_lines = [_format_event_line(e) for e in events]

    return "\n".join(header_lines + body_lines) + "\n"
