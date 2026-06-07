from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity

from services.live_room_service import get_recent_room_events, list_online_participants, user_can_access_room
from utils.response import ok, fail

live_room_bp = Blueprint("live_room_bp", __name__)


@live_room_bp.get("/rooms/<room_code>/events")
@jwt_required(optional=True)
def room_events(room_code):
    user_id = get_jwt_identity()
    if user_id and not user_can_access_room(room_code, user_id=user_id):
        return fail("You cannot access this live room", 403)
    return ok("Live room events fetched", {"events": get_recent_room_events(room_code)})


@live_room_bp.get("/rooms/<room_code>/participants")
@jwt_required(optional=True)
def room_participants(room_code):
    user_id = get_jwt_identity()
    if user_id and not user_can_access_room(room_code, user_id=user_id):
        return fail("You cannot access this live room", 403)
    return ok("Live room participants fetched", {"participants": list_online_participants(room_code)})
