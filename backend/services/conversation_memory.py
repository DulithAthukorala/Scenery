from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from typing import Any, Dict, List
from uuid import uuid4

from backend.config import (
    REDIS_ENABLED,
    REDIS_MAX_TURNS,
    REDIS_SESSION_TTL_SECONDS,
    REDIS_URL,
)

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis_async
except Exception:  # pragma: no cover
    redis_async = None


_PREFIX = "scenery:session"
_redis_client = None
_REDIS_FAILURE_COOLDOWN_SECONDS = 60
_redis_disabled_until_ts = 0.0
_fallback_sessions: Dict[str, Dict[str, Any]] = {}


def _session_key(session_id: str) -> str:
    return f"{_PREFIX}:{session_id}"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _merge_slots(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if value is None:
            continue
        merged[key] = _to_jsonable(value)
    return merged


def _build_default_context(session_id: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "conversation_id": str(uuid4()),
        "slots": {},
        "turns": [],
        "last_action": None,
        "memory_enabled": False,
    }


async def _get_redis_client():
    global _redis_client, _redis_disabled_until_ts
    if not REDIS_ENABLED or redis_async is None:
        return None

    if time.time() < _redis_disabled_until_ts:
        return None

    if _redis_client is None:
        _redis_client = redis_async.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
            retry_on_timeout=False,
        )

    return _redis_client


def _get_fallback_context(session_id: str) -> Dict[str, Any]:
    now = time.time()
    entry = _fallback_sessions.get(session_id)
    if not entry:
        return _build_default_context(session_id)

    expires_at = float(entry.get("expires_at") or 0)
    if expires_at < now:
        _fallback_sessions.pop(session_id, None)
        return _build_default_context(session_id)

    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    turns = payload.get("turns") if isinstance(payload.get("turns"), list) else []
    slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}

    return {
        "session_id": session_id,
        "conversation_id": payload.get("conversation_id") or str(uuid4()),
        "slots": slots,
        "turns": turns,
        "last_action": payload.get("last_action"),
        "memory_enabled": True,
    }


def _set_fallback_context(context: Dict[str, Any]) -> None:
    session_id = str(context.get("session_id") or "").strip()
    if not session_id:
        return

    _fallback_sessions[session_id] = {
        "expires_at": time.time() + REDIS_SESSION_TTL_SECONDS,
        "payload": {
            "conversation_id": context.get("conversation_id"),
            "slots": context.get("slots") or {},
            "turns": context.get("turns") or [],
            "last_action": context.get("last_action"),
            "updated_at": int(time.time()),
        },
    }


async def get_session_context(session_id: str) -> Dict[str, Any]:
    context = _build_default_context(session_id)
    client = await _get_redis_client()
    if client is None:
        return _get_fallback_context(session_id)

    try:
        raw = await client.get(_session_key(session_id))
        if not raw:
            return _get_fallback_context(session_id)

        payload = json.loads(raw)
        turns = payload.get("turns") if isinstance(payload.get("turns"), list) else []
        slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}

        context.update(
            {
                "conversation_id": payload.get("conversation_id") or context["conversation_id"],
                "slots": slots,
                "turns": turns,
                "last_action": payload.get("last_action"),
                "memory_enabled": True,
            }
        )
        return context
    except Exception as exc:
        global _redis_disabled_until_ts
        _redis_disabled_until_ts = time.time() + _REDIS_FAILURE_COOLDOWN_SECONDS
        logger.warning("conversation_memory_read_failed session_id=%s error=%s", session_id, str(exc))
        return _get_fallback_context(session_id)


async def save_session_turn(
    session_id: str,
    user_text: str,
    assistant_text: str,
    result_payload: Dict[str, Any],
    existing_context: Dict[str, Any],
) -> Dict[str, Any]:
    conversation_id = (
        existing_context.get("conversation_id")
        if isinstance(existing_context, dict)
        else None
    ) or str(uuid4())

    base_slots = existing_context.get("slots") if isinstance(existing_context, dict) else {}
    incoming_slots = result_payload.get("slots") if isinstance(result_payload, dict) else {}
    merged_slots = _merge_slots(base_slots if isinstance(base_slots, dict) else {}, incoming_slots if isinstance(incoming_slots, dict) else {})

    old_turns = existing_context.get("turns") if isinstance(existing_context, dict) else []
    turns: List[Dict[str, Any]] = old_turns if isinstance(old_turns, list) else []

    now_ts = int(time.time())
    turns = [
        *turns,
        {"role": "user", "text": user_text, "timestamp": now_ts},
        {
            "role": "assistant",
            "text": assistant_text,
            "action": result_payload.get("action") if isinstance(result_payload, dict) else None,
            "timestamp": now_ts,
        },
    ]

    max_events = max(2, REDIS_MAX_TURNS * 2)
    if len(turns) > max_events:
        turns = turns[-max_events:]

    context_out = {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "slots": merged_slots,
        "turns": turns,
        "last_action": result_payload.get("action") if isinstance(result_payload, dict) else None,
        "memory_enabled": True,
    }

    _set_fallback_context(context_out)

    client = await _get_redis_client()
    if client is None:
        return context_out

    try:
        payload = {
            "conversation_id": conversation_id,
            "slots": merged_slots,
            "turns": turns,
            "last_action": context_out.get("last_action"),
            "updated_at": now_ts,
        }
        await client.set(_session_key(session_id), json.dumps(_to_jsonable(payload), ensure_ascii=False), ex=REDIS_SESSION_TTL_SECONDS)
        return context_out
    except Exception as exc:
        global _redis_disabled_until_ts
        _redis_disabled_until_ts = time.time() + _REDIS_FAILURE_COOLDOWN_SECONDS
        logger.warning("conversation_memory_write_failed session_id=%s error=%s", session_id, str(exc))
        return context_out
