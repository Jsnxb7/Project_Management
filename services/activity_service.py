from datetime import datetime, timezone

from database.db import activity_logs_collection
from services.hrms_service import to_object_id


def log_activity(actor_id, action_type, description, category="General", entity_type=None, entity_id=None, metadata=None):
    activity_logs_collection.insert_one({
        "scope": "HRMS",
        "category": category,
        "actor_id": to_object_id(actor_id),
        "action_type": action_type,
        "description": description,
        "entity_type": entity_type,
        "entity_id": to_object_id(entity_id) if entity_id else None,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc),
    })
