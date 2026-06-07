from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId

from database.db import (
    interview_rooms_collection,
    interview_sessions_collection,
    users_collection,
    live_room_events_collection,
    live_room_participants_collection,
    webrtc_signals_collection,
)


def utcnow() -> str:
    return datetime.utcnow().isoformat()


def as_str(value):
    return str(value) if value is not None else None


def to_object_id(value):
    if not value:
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return value


def serialize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    out = dict(doc)
    for key, value in list(out.items()):
        if isinstance(value, ObjectId):
            out[key] = str(value)
    return out


def get_room(room_code: str) -> Optional[Dict[str, Any]]:
    return interview_rooms_collection.find_one({"room_code": room_code})


def get_session(room: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sid = room.get("session_id") if room else None
    return interview_sessions_collection.find_one({"_id": sid}) if sid else None


def get_user(user_id) -> Optional[Dict[str, Any]]:
    oid = to_object_id(user_id)
    query = {"_id": oid} if isinstance(oid, ObjectId) else {"$or": [{"_id": oid}, {"candidate_uid": oid}, {"email": oid}]}
    return users_collection.find_one(query)


def user_can_access_room(room_code: str, user_id=None, email=None, role=None) -> bool:
    room = get_room(room_code)
    if not room:
        return False
    session = get_session(room)
    participants = {str(x) for x in (room.get("participants") or []) if x}
    if user_id and str(user_id) in participants:
        return True
    if email and str(email) in participants:
        return True
    if session:
        session_ids = [session.get("candidate_user_id"), session.get("interviewer_user_id"), session.get("created_by")]
        session_ids.extend(session.get("panel_user_ids") or [])
        if user_id and str(user_id) in {str(x) for x in session_ids if x}:
            return True
        if email and email in {session.get("candidate_email"), session.get("interviewer_email")}:
            return True
    if role in {"Super User", "Admin", "Org Head", "HR", "Controller"}:
        return True
    return False


def mark_participant_online(room_code: str, user_id, socket_id: str, display_name: str = "", role: str = "") -> Dict[str, Any]:
    doc = {
        "room_code": room_code,
        "user_id": as_str(user_id),
        "socket_id": socket_id,
        "display_name": display_name,
        "role": role,
        "online": True,
        "joined_at": utcnow(),
        "last_seen_at": utcnow(),
    }
    live_room_participants_collection.update_one(
        {"room_code": room_code, "user_id": as_str(user_id), "socket_id": socket_id},
        {"$set": doc},
        upsert=True,
    )
    return doc


def mark_participant_offline(socket_id: str):
    live_room_participants_collection.update_many(
        {"socket_id": socket_id},
        {"$set": {"online": False, "left_at": utcnow(), "last_seen_at": utcnow()}},
    )


def list_online_participants(room_code: str):
    return [serialize_doc(x) for x in live_room_participants_collection.find({"room_code": room_code, "online": True})]


def save_room_event(room_code: str, event_type: str, payload: Dict[str, Any] | None = None, actor_user_id=None) -> Dict[str, Any]:
    doc = {
        "room_code": room_code,
        "event_type": event_type,
        "payload": payload or {},
        "actor_user_id": as_str(actor_user_id),
        "created_at": utcnow(),
    }
    res = live_room_events_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize_doc(doc)


def get_recent_room_events(room_code: str, limit: int = 100):
    return [serialize_doc(x) for x in live_room_events_collection.find({"room_code": room_code}).sort("created_at", -1).limit(limit)]


def save_webrtc_signal(room_code: str, signal_type: str, payload: Dict[str, Any], from_user_id=None, to_user_id=None) -> Dict[str, Any]:
    doc = {
        "room_code": room_code,
        "signal_type": signal_type,
        "payload": payload or {},
        "from_user_id": as_str(from_user_id),
        "to_user_id": as_str(to_user_id),
        "created_at": utcnow(),
    }
    res = webrtc_signals_collection.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize_doc(doc)
