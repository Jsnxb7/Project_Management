from datetime import datetime, timezone

from database.db import notifications_collection
from services.hrms_service import to_object_id


def create_notification(user_id, message, notification_type="Info", category="HRMS", entity_type=None, entity_id=None):
    if not user_id:
        return
    notifications_collection.insert_one({
        "user_id": to_object_id(user_id),
        "message": message,
        "type": notification_type,
        "category": category,
        "entity_type": entity_type,
        "entity_id": to_object_id(entity_id) if entity_id else None,
        "is_read": False,
        "created_at": datetime.now(timezone.utc),
    })
