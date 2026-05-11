from pymongo import MongoClient, ASCENDING, DESCENDING
from config import Config

if not Config.MONGO_URI:
    raise RuntimeError("MONGO_URI is missing. Create a .env file using .env.example.")

client = MongoClient(Config.MONGO_URI)
db = client[Config.DB_NAME]

users_collection = db["users"]
projects_collection = db["projects"]
tasks_collection = db["tasks"]
comments_collection = db["comments"]
notifications_collection = db["notifications"]
activity_logs_collection = db["activity_logs"]
organizations_collection = db["organizations"]
login_sessions_collection = db["login_sessions"]
attachments_collection = db["attachments"]
subtasks_collection = db["subtasks"]
user_org_memberships_collection = db["user_org_memberships"]
milestones_collection = db["milestones"]
teams_collection = db["teams"]


def ensure_performance_indexes():
    """Create safe non-destructive indexes used by list/search-heavy pages."""
    try:
        users_collection.create_index([("email", ASCENDING)], background=True)
        users_collection.create_index([("is_active", ASCENDING), ("portal_role", ASCENDING)], background=True)
        users_collection.create_index([("name", ASCENDING)], background=True)

        organizations_collection.create_index([("status", ASCENDING), ("updated_at", DESCENDING)], background=True)
        organizations_collection.create_index([("members.user_id", ASCENDING), ("members.status", ASCENDING)], background=True)
        organizations_collection.create_index([("name", ASCENDING)], background=True)

        projects_collection.create_index([("status", ASCENDING), ("updated_at", DESCENDING)], background=True)
        projects_collection.create_index([("organization_id", ASCENDING), ("status", ASCENDING)], background=True)
        projects_collection.create_index([("members.user_id", ASCENDING), ("members.status", ASCENDING)], background=True)
        projects_collection.create_index([("team_assignments.team_id", ASCENDING)], background=True)

        teams_collection.create_index([("organization_id", ASCENDING), ("status", ASCENDING)], background=True)
        teams_collection.create_index([("members.user_id", ASCENDING), ("members.status", ASCENDING)], background=True)
        teams_collection.create_index([("team_lead_id", ASCENDING), ("status", ASCENDING)], background=True)

        tasks_collection.create_index([("project_id", ASCENDING), ("is_deleted", ASCENDING)], background=True)
        tasks_collection.create_index([("project_id", ASCENDING), ("status", ASCENDING), ("is_deleted", ASCENDING)], background=True)
        tasks_collection.create_index([("assigned_to", ASCENDING), ("is_deleted", ASCENDING)], background=True)
        tasks_collection.create_index([("due_date", ASCENDING), ("status", ASCENDING)], background=True)

        notifications_collection.create_index([("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)], background=True)
        activity_logs_collection.create_index([("project_id", ASCENDING), ("created_at", DESCENDING)], background=True)
        comments_collection.create_index([("project_id", ASCENDING), ("created_at", DESCENDING)], background=True)
        attachments_collection.create_index([("project_id", ASCENDING), ("created_at", DESCENDING)], background=True)
        milestones_collection.create_index([("project_id", ASCENDING), ("status", ASCENDING)], background=True)
    except Exception as exc:
        print(f"[DB] Index creation skipped/failed: {exc}")


ensure_performance_indexes()
