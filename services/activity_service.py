from datetime import datetime, timezone
from bson import ObjectId
from database.db import activity_logs_collection


def oid(value):
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    return ObjectId(value)


def log_activity(project_id, user_id, action_type, description, task_id=None):
    activity_logs_collection.insert_one({
        "project_id": oid(project_id),
        "task_id": oid(task_id) if task_id else None,
        "user_id": oid(user_id),
        "action_type": action_type,
        "description": description,
        "created_at": datetime.now(timezone.utc),
    })
