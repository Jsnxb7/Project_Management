from datetime import datetime, timezone
from bson import ObjectId
from database.db import notifications_collection


def oid(value):
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    return ObjectId(value)


def create_notification(user_id, message, notification_type, project_id=None, task_id=None):
    if not user_id:
        return

    notifications_collection.insert_one({
        "user_id": oid(user_id),
        "project_id": oid(project_id) if project_id else None,
        "task_id": oid(task_id) if task_id else None,
        "message": message,
        "type": notification_type,
        "is_read": False,
        "created_at": datetime.now(timezone.utc),
    })
