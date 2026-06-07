from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId

from database.db import notifications_collection
from utils.response import ok, fail
from services.hrms_service import to_object_id

notification_bp = Blueprint("notification_bp", __name__)


def notification_public(notification):
    return {
        "id": str(notification["_id"]),
        "message": notification.get("message"),
        "type": notification.get("type"),
        "category": notification.get("category", "HRMS"),
        "is_read": notification.get("is_read", False),
        "entity_type": notification.get("entity_type"),
        "entity_id": str(notification["entity_id"]) if notification.get("entity_id") else None,
        "created_at": notification["created_at"].isoformat() if notification.get("created_at") else None,
    }


def _page_args(default_limit=20, max_limit=100):
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = max(1, min(int(request.args.get("limit", default_limit)), max_limit))
    except (TypeError, ValueError):
        limit = default_limit
    return page, limit, (page - 1) * limit


def _meta(total, page, limit):
    pages = max(1, (int(total or 0) + limit - 1) // limit)
    return {"page": page, "limit": limit, "total": int(total or 0), "pages": pages, "has_next": page < pages, "has_prev": page > 1}


@notification_bp.get("")
@jwt_required()
def get_notifications():
    user_id = ObjectId(get_jwt_identity())
    page, limit, skip = _page_args(default_limit=20, max_limit=100)
    query = {"user_id": user_id}

    total = notifications_collection.count_documents(query)
    notifications = list(
        notifications_collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
    )

    unread_count = notifications_collection.count_documents({
        "user_id": user_id,
        "is_read": False
    })

    return ok("Notifications fetched", {
        "notifications": [notification_public(n) for n in notifications],
        "unread_count": unread_count,
        "meta": _meta(total, page, limit),
    })


@notification_bp.patch("/<notification_id>/read")
@jwt_required()
def mark_notification_read(notification_id):
    user_id = ObjectId(get_jwt_identity())
    notification_obj_id = to_object_id(notification_id)

    if not notification_obj_id:
        return fail("Invalid notification id")

    result = notifications_collection.update_one(
        {"_id": notification_obj_id, "user_id": user_id},
        {"$set": {"is_read": True}}
    )

    if result.matched_count == 0:
        return fail("Notification not found", 404)

    return ok("Notification marked as read")


@notification_bp.patch("/read-all")
@jwt_required()
def mark_all_read():
    user_id = ObjectId(get_jwt_identity())

    notifications_collection.update_many(
        {"user_id": user_id, "is_read": False},
        {"$set": {"is_read": True}}
    )

    return ok("All notifications marked as read")
