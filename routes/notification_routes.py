from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId

from database.db import notifications_collection
from utils.response import ok, fail
from services.permission_service import to_object_id

notification_bp = Blueprint("notification_bp", __name__)


def notification_public(notification):
    return {
        "id": str(notification["_id"]),
        "message": notification.get("message"),
        "type": notification.get("type"),
        "is_read": notification.get("is_read", False),
        "project_id": str(notification["project_id"]) if notification.get("project_id") else None,
        "task_id": str(notification["task_id"]) if notification.get("task_id") else None,
        "created_at": notification["created_at"].isoformat() if notification.get("created_at") else None,
    }


@notification_bp.get("")
@jwt_required()
def get_notifications():
    user_id = ObjectId(get_jwt_identity())

    notifications = list(
        notifications_collection.find({"user_id": user_id}).sort("created_at", -1).limit(50)
    )

    unread_count = notifications_collection.count_documents({
        "user_id": user_id,
        "is_read": False
    })

    return ok("Notifications fetched", {
        "notifications": [notification_public(n) for n in notifications],
        "unread_count": unread_count,
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
