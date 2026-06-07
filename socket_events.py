"""Windows-safe Socket.IO event setup for AI/personal/HR interview rooms.

Drop this file over the current socket_events.py or merge the events into it.
Important fixes:
- Uses async_mode='threading' for Windows/Python 3.11+ stability.
- Does not use eventlet/gevent.
- Avoids duplicate handler registration when Flask debug reloads.
- Supports WebRTC signalling and AI room live updates.
"""
from __future__ import annotations

from flask import request
from flask_socketio import SocketIO, join_room, leave_room, emit

socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)

_EVENTS_REGISTERED = False


def init_socket_events(app):
    """Initialize Socket.IO once. Call this inside create_app(app)."""
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
        ping_timeout=60,
        ping_interval=25,
    )
    register_socket_events()
    return socketio


def register_socket_events():
    global _EVENTS_REGISTERED
    if _EVENTS_REGISTERED:
        return
    _EVENTS_REGISTERED = True

    @socketio.on("connect")
    def handle_connect(auth=None):
        emit("socket_ready", {"sid": request.sid})

    @socketio.on("disconnect")
    def handle_disconnect():
        # Keep this lightweight. Presence cleanup can be added later with Mongo.
        pass

    @socketio.on("join_interview_room")
    def handle_join_interview_room(data):
        room_code = (data or {}).get("room_code")
        user_id = (data or {}).get("user_id")
        role = (data or {}).get("role")
        if not room_code:
            return
        join_room(room_code)
        emit("room_user_joined", {
            "room_code": room_code,
            "user_id": user_id,
            "role": role,
            "sid": request.sid,
        }, room=room_code, include_self=False)
        emit("room_joined", {"room_code": room_code, "sid": request.sid})

    @socketio.on("leave_interview_room")
    def handle_leave_interview_room(data):
        room_code = (data or {}).get("room_code")
        user_id = (data or {}).get("user_id")
        role = (data or {}).get("role")
        if not room_code:
            return
        leave_room(room_code)
        emit("room_user_left", {
            "room_code": room_code,
            "user_id": user_id,
            "role": role,
            "sid": request.sid,
        }, room=room_code, include_self=False)

    @socketio.on("ai_room_update")
    def handle_ai_room_update(data):
        room_code = (data or {}).get("room_code")
        if room_code:
            emit("ai_room_update", data, room=room_code)

    @socketio.on("ai_question_ready")
    def handle_ai_question_ready(data):
        room_code = (data or {}).get("room_code")
        if room_code:
            emit("ai_question_ready", data, room=room_code)

    @socketio.on("ai_answer_saved")
    def handle_ai_answer_saved(data):
        room_code = (data or {}).get("room_code")
        if room_code:
            emit("ai_answer_saved", data, room=room_code)

    # WebRTC signalling for personal / HR interview rooms.
    @socketio.on("webrtc_offer")
    def handle_webrtc_offer(data):
        room_code = (data or {}).get("room_code")
        if room_code:
            emit("webrtc_offer", data, room=room_code, include_self=False)

    @socketio.on("webrtc_answer")
    def handle_webrtc_answer(data):
        room_code = (data or {}).get("room_code")
        if room_code:
            emit("webrtc_answer", data, room=room_code, include_self=False)

    @socketio.on("webrtc_ice_candidate")
    def handle_webrtc_ice_candidate(data):
        room_code = (data or {}).get("room_code")
        if room_code:
            emit("webrtc_ice_candidate", data, room=room_code, include_self=False)
