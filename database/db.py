from __future__ import annotations

"""Local MongoDB-only database layer.

This replaces the older Atlas + JSON mirror hybrid.  The app now treats a local
MongoDB server as the only source of truth.  JSON files may still exist in the
repository for backups or one-time migration, but runtime reads/writes never use
or mirror to JSON.
"""

import os
from typing import Iterable

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

from config import Config


COLLECTION_NAMES = [
    # Core users and people
    "users",
    "employees",
    "employee_documents",

    # Attendance and leave
    "attendance",
    "hrms_attendance_rules",
    "hrms_attendance_corrections",
    "hrms_attendance_meetings",
    "hrms_attendance_reviews",
    "hrms_leave_requests",
    "hrms_manager_assignments",
    "leave_requests",

    # Payroll + performance
    "hrms_payroll_profiles",
    "hrms_payroll_cycles",
    "hrms_payroll_items",
    "hrms_payroll_adjustments",
    "hrms_payouts",
    "hrms_payroll_queries",
    "hrms_performance_templates",
    "hrms_performance_goals",
    "hrms_performance_checklists",
    "hrms_performance_scores",

    # Legacy aliases still referenced by older routes/services
    "payroll",
    "performance_reviews",
    "hrms_performance_cycles",
    "hrms_performance_milestones",
    "hrms_performance_feedback",

    # Recruitment
    "jobs",
    "job_knowledge_base",
    "applications",
    "resume_screening_results",
    "recruitment_candidates",
    "interview_sessions",
    "interview_messages",
    "interview_rooms",
    "candidate_processes",
    "ai_interview_configs",
    "ai_interview_transcripts",
    "ai_interview_results",
    "ai_interview_model_events",

    # Live rooms / signalling
    "live_room_events",
    "live_room_participants",
    "webrtc_signals",

    # Communication/system
    "hrms_messages",
    "notifications",
    "activity_logs",
    "login_sessions",
    "hrms_audit_logs",

    # HR support and UI/theme
    "hr_cases",
    "learning_records",
    "user_themes",
    "hrms_ui_settings",
    "hrms_ui_page_groups",
]

# Backward-compatible map for migration scripts only.  Runtime does not use it.
COLLECTION_REGISTRY = {name: f"{name}.json" for name in COLLECTION_NAMES}

client = MongoClient(
    Config.MONGO_URI,
    maxPoolSize=int(os.getenv("MONGO_MAX_POOL_SIZE", "200")),
    minPoolSize=int(os.getenv("MONGO_MIN_POOL_SIZE", "5")),
    serverSelectionTimeoutMS=int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "20000")),
    connectTimeoutMS=int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "20000")),
    retryWrites=os.getenv("MONGO_RETRY_WRITES", "true").lower() == "true",
)
db = client[Config.DB_NAME]


def get_collection(name: str) -> Collection:
    return db[name]


def check_mongo_connection() -> dict:
    try:
        client.admin.command("ping")
        return {"ok": True, "uri": Config.MONGO_URI, "database": Config.DB_NAME}
    except ServerSelectionTimeoutError as exc:
        return {"ok": False, "uri": Config.MONGO_URI, "database": Config.DB_NAME, "error": str(exc)}


def ensure_index(collection: Collection, keys, **options):
    """Create indexes safely.

    If an old index exists with the same auto-generated name but different
    options, MongoDB can throw IndexKeySpecsConflict.  For this app we ignore
    duplicate/conflicting index creation because the collection remains usable.
    """
    try:
        return collection.create_index(keys, background=True, **options)
    except OperationFailure:
        return None
    except Exception:
        return None


def ensure_local_mongo_indexes(collection_names: Iterable[str] | None = None):
    names = set(collection_names or COLLECTION_NAMES)
    index_plan = {
        "users": [[("email", ASCENDING)], [("username", ASCENDING)], [("hrms_role", ASCENDING)], [("is_active", ASCENDING), ("name", ASCENDING)]],
        "employees": [[("email", ASCENDING)], [("employee_id", ASCENDING)], [("name", ASCENDING)], [("manager_ids", ASCENDING)]],
        "jobs": [[("status", ASCENDING)], [("created_at", DESCENDING)], [("status", ASCENDING), ("open_until", ASCENDING), ("created_at", DESCENDING)], [("created_by", ASCENDING), ("created_at", DESCENDING)], [("controller_user_ids", ASCENDING), ("created_at", DESCENDING)], [("viewer_user_ids", ASCENDING), ("created_at", DESCENDING)]],
        "applications": [[("candidate_email", ASCENDING)], [("job_id", ASCENDING)], [("room_code", ASCENDING)], [("candidate_user_id", ASCENDING)], [("ai_interview_status", ASCENDING)], [("job_id", ASCENDING), ("final_score", DESCENDING), ("created_at", DESCENDING)], [("status", ASCENDING), ("updated_at", DESCENDING)], [("review_status", ASCENDING), ("created_at", DESCENDING)]],
        "resume_screening_results": [[("application_id", ASCENDING)], [("candidate_email", ASCENDING)]],
        "recruitment_candidates": [[("application_id", ASCENDING)], [("candidate_user_id", ASCENDING)]],
        "interview_rooms": [[("room_code", ASCENDING)], [("session_id", ASCENDING)], [("room_type", ASCENDING)], [("status", ASCENDING)], [("participants", ASCENDING)]],
        "interview_sessions": [[("room_code", ASCENDING)], [("application_id", ASCENDING)], [("candidate_user_id", ASCENDING)], [("interviewer_user_id", ASCENDING)], [("scheduled_at", DESCENDING)], [("created_at", DESCENDING)], [("candidate_email", ASCENDING), ("created_at", DESCENDING)]],
        "interview_messages": [[("room_code", ASCENDING)], [("created_at", DESCENDING)]],
        "ai_interview_configs": [[("room_code", ASCENDING)]],
        "ai_interview_transcripts": [[("room_code", ASCENDING)], [("status", ASCENDING)], [("started_at", DESCENDING)], [("room_code", ASCENDING), ("started_at", DESCENDING)], [("room_code", ASCENDING), ("status", ASCENDING)]],
        "ai_interview_results": [[("room_code", ASCENDING)], [("application_id", ASCENDING)], [("created_at", DESCENDING)], [("room_code", ASCENDING), ("created_at", DESCENDING)], [("transcript_id", ASCENDING)]],
        "live_room_events": [[("room_code", ASCENDING)], [("created_at", DESCENDING)], [("event_type", ASCENDING)]],
        "live_room_participants": [[("room_code", ASCENDING)], [("user_id", ASCENDING)], [("socket_id", ASCENDING)], [("last_seen_at", DESCENDING)]],
        "webrtc_signals": [[("room_code", ASCENDING)], [("to_user_id", ASCENDING)], [("created_at", DESCENDING)]],
        "notifications": [[("user_id", ASCENDING)], [("created_at", DESCENDING)], [("user_id", ASCENDING), ("created_at", DESCENDING)], [("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)]],
        "hrms_messages": [[("participant_user_ids", ASCENDING), ("updated_at", DESCENDING)], [("conversation_key", ASCENDING), ("created_at", DESCENDING)], [("sender_user_id", ASCENDING)], [("receiver_user_id", ASCENDING)]],
        "hrms_payroll_items": [[("employee_id", ASCENDING), ("cycle_key", DESCENDING)], [("status", ASCENDING), ("cycle_key", DESCENDING)], [("payout_status", ASCENDING), ("cycle_key", DESCENDING)]],
        "hrms_payroll_adjustments": [[("employee_id", ASCENDING), ("created_at", DESCENDING)], [("included", ASCENDING), ("created_at", DESCENDING)]],
        "hrms_payroll_profiles": [[("employee_id", ASCENDING)], [("updated_at", DESCENDING)]],
        "hrms_performance_goals": [[("employee_id", ASCENDING), ("created_at", DESCENDING)], [("status", ASCENDING), ("created_at", DESCENDING)], [("cycle_key", DESCENDING)]],
        "hrms_performance_templates": [[("name", ASCENDING)], [("department", ASCENDING), ("name", ASCENDING)]],
        "login_sessions": [[("user_id", ASCENDING)], [("created_at", DESCENDING)]],
        "activity_logs": [[("user_id", ASCENDING)], [("created_at", DESCENDING)]],
        "hrms_audit_logs": [[("actor_user_id", ASCENDING)], [("created_at", DESCENDING)]],
    }
    for collection_name, indexes in index_plan.items():
        if collection_name not in names:
            continue
        collection = db[collection_name]
        for keys in indexes:
            ensure_index(collection, keys)


def ensure_performance_indexes():
    ensure_local_mongo_indexes()


def has_duplicate_values(collection: Collection, field: str) -> bool:
    duplicates = list(collection.aggregate([
        {"$match": {field: {"$type": "string", "$ne": ""}}},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 1},
    ]))
    return bool(duplicates)


# Collection exports used throughout the project.
users_collection = get_collection("users")
notifications_collection = get_collection("notifications")
activity_logs_collection = get_collection("activity_logs")
login_sessions_collection = get_collection("login_sessions")
employees_collection = get_collection("employees")
attendance_collection = get_collection("attendance")
payroll_collection = get_collection("payroll")
performance_reviews_collection = get_collection("performance_reviews")
leave_requests_collection = get_collection("leave_requests")
recruitment_candidates_collection = get_collection("recruitment_candidates")
employee_documents_collection = get_collection("employee_documents")
hr_cases_collection = get_collection("hr_cases")
learning_records_collection = get_collection("learning_records")
jobs_collection = get_collection("jobs")
job_knowledge_collection = get_collection("job_knowledge_base")
applications_collection = get_collection("applications")
resume_screening_collection = get_collection("resume_screening_results")
interview_sessions_collection = get_collection("interview_sessions")
interview_messages_collection = get_collection("interview_messages")
interview_rooms_collection = get_collection("interview_rooms")
candidate_processes_collection = get_collection("candidate_processes")
ai_interview_configs_collection = get_collection("ai_interview_configs")
ai_interview_transcripts_collection = get_collection("ai_interview_transcripts")
ai_interview_results_collection = get_collection("ai_interview_results")
ai_interview_model_events_collection = get_collection("ai_interview_model_events")
live_room_events_collection = get_collection("live_room_events")
live_room_participants_collection = get_collection("live_room_participants")
webrtc_signals_collection = get_collection("webrtc_signals")
user_theme_collection = get_collection("user_themes")
hrms_messages_collection = get_collection("hrms_messages")
hrms_attendance_rules_collection = get_collection("hrms_attendance_rules")
hrms_manager_assignments_collection = get_collection("hrms_manager_assignments")
hrms_attendance_reviews_collection = get_collection("hrms_attendance_reviews")
hrms_attendance_meetings_collection = get_collection("hrms_attendance_meetings")
hrms_attendance_corrections_collection = get_collection("hrms_attendance_corrections")
hrms_audit_logs_collection = get_collection("hrms_audit_logs")
hrms_payroll_profiles_collection = get_collection("hrms_payroll_profiles")
hrms_payroll_cycles_collection = get_collection("hrms_payroll_cycles")
hrms_payroll_items_collection = get_collection("hrms_payroll_items")
hrms_payroll_adjustments_collection = get_collection("hrms_payroll_adjustments")
hrms_payouts_collection = get_collection("hrms_payouts")
hrms_payroll_queries_collection = get_collection("hrms_payroll_queries")
hrms_performance_cycles_collection = get_collection("hrms_performance_cycles")
hrms_performance_templates_collection = get_collection("hrms_performance_templates")
hrms_performance_goals_collection = get_collection("hrms_performance_goals")
hrms_performance_milestones_collection = get_collection("hrms_performance_milestones")
hrms_performance_checklists_collection = get_collection("hrms_performance_checklists")
hrms_performance_scores_collection = get_collection("hrms_performance_scores")
hrms_performance_feedback_collection = get_collection("hrms_performance_feedback")

# Legacy project-management collections kept as direct Mongo exports for old repair scripts.
organizations_collection = get_collection("organizations")
projects_collection = get_collection("projects")
tasks_collection = get_collection("tasks")
teams_collection = get_collection("teams")
user_org_memberships_collection = get_collection("user_org_memberships")
