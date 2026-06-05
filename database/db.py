from pymongo import MongoClient, ASCENDING, DESCENDING
from config import Config

if not Config.MONGO_URI:
    raise RuntimeError("MONGO_URI is missing. Create a .env file using .env.example.")

client = MongoClient(
    Config.MONGO_URI,
    maxPoolSize=200,
    minPoolSize=5,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    retryWrites=True,
)
db = client[Config.DB_NAME]

users_collection = db["users"]
notifications_collection = db["notifications"]
activity_logs_collection = db["activity_logs"]
login_sessions_collection = db["login_sessions"]
employees_collection = db["employees"]
attendance_collection = db["attendance"]
payroll_collection = db["payroll"]
performance_reviews_collection = db["performance_reviews"]
leave_requests_collection = db["leave_requests"]
recruitment_candidates_collection = db["recruitment_candidates"]
employee_documents_collection = db["employee_documents"]
hr_cases_collection = db["hr_cases"]
learning_records_collection = db["learning_records"]
jobs_collection = db["jobs"]
job_knowledge_collection = db["job_knowledge_base"]
applications_collection = db["applications"]
resume_screening_collection = db["resume_screening_results"]
interview_sessions_collection = db["interview_sessions"]
interview_messages_collection = db["interview_messages"]
interview_rooms_collection = db["interview_rooms"]
user_theme_collection = db["user_themes"]
hrms_messages_collection = db["hrms_messages"]
hrms_attendance_rules_collection = db["hrms_attendance_rules"]
hrms_manager_assignments_collection = db["hrms_manager_assignments"]
hrms_attendance_reviews_collection = db["hrms_attendance_reviews"]
hrms_attendance_meetings_collection = db["hrms_attendance_meetings"]
hrms_attendance_corrections_collection = db["hrms_attendance_corrections"]
hrms_audit_logs_collection = db["hrms_audit_logs"]


def has_duplicate_values(collection, field):
    duplicates = list(collection.aggregate([
        {"$match": {field: {"$type": "string", "$ne": ""}}},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 1},
    ]))
    return bool(duplicates)


def ensure_index(collection, keys, **options):
    name = options.get("name") or "_".join(f"{field}_{direction}" for field, direction in keys)
    indexes = collection.index_information()
    existing = indexes.get(name)
    requested_unique = bool(options.get("unique"))
    requested_sparse = bool(options.get("sparse"))
    requested_key = list(keys)

    for existing_index in indexes.values():
        if list(existing_index.get("key", [])) != requested_key:
            continue
        if bool(existing_index.get("unique")) != requested_unique:
            continue
        if bool(existing_index.get("sparse")) != requested_sparse:
            continue
        return

    if existing and requested_unique and not existing.get("unique"):
        fields = [field for field, _ in keys]
        if len(fields) == 1 and has_duplicate_values(collection, fields[0]):
            print(f"[DB] Unique index {collection.name}.{name} not upgraded because duplicate {fields[0]} values exist.")
            return
        collection.drop_index(name)

    try:
        collection.create_index(keys, **options)
    except Exception as exc:
        print(f"[DB] Index creation skipped/failed for {collection.name}.{name}: {exc}")


def ensure_performance_indexes():
    """Create safe non-destructive indexes for HRMS data access."""
    ensure_index(users_collection, [("email", ASCENDING)], unique=True, background=True)
    ensure_index(users_collection, [("is_active", ASCENDING), ("hrms_role", ASCENDING)], background=True)
    ensure_index(users_collection, [("name", ASCENDING)], background=True)
    ensure_index(users_collection, [("candidate_uid", ASCENDING)], sparse=True, background=True)

    ensure_index(notifications_collection, [("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(notifications_collection, [("category", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(activity_logs_collection, [("scope", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(activity_logs_collection, [("actor_id", ASCENDING), ("created_at", DESCENDING)], background=True)

    ensure_index(employees_collection, [("user_id", ASCENDING)], background=True)
    ensure_index(employees_collection, [("employee_code", ASCENDING)], unique=True, sparse=True, background=True)
    ensure_index(employees_collection, [("department", ASCENDING), ("employment_status", ASCENDING)], background=True)
    ensure_index(employees_collection, [("manager_id", ASCENDING), ("employment_status", ASCENDING)], background=True)

    ensure_index(attendance_collection, [("employee_id", ASCENDING), ("date", DESCENDING)], background=True)
    ensure_index(attendance_collection, [("employee_id", ASCENDING), ("date_key", DESCENDING)], background=True)
    ensure_index(attendance_collection, [("department", ASCENDING), ("date", DESCENDING)], background=True)
    ensure_index(attendance_collection, [("status", ASCENDING), ("date", DESCENDING)], background=True)

    ensure_index(payroll_collection, [("employee_id", ASCENDING), ("period", DESCENDING)], background=True)
    ensure_index(payroll_collection, [("status", ASCENDING), ("period", DESCENDING)], background=True)

    ensure_index(performance_reviews_collection, [("employee_id", ASCENDING), ("review_period", DESCENDING)], background=True)
    ensure_index(performance_reviews_collection, [("manager_id", ASCENDING), ("status", ASCENDING)], background=True)

    ensure_index(leave_requests_collection, [("employee_id", ASCENDING), ("status", ASCENDING), ("start_date", DESCENDING)], background=True)
    ensure_index(recruitment_candidates_collection, [("status", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(recruitment_candidates_collection, [("job_title", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(recruitment_candidates_collection, [("candidate_email", ASCENDING)], background=True)
    ensure_index(recruitment_candidates_collection, [("candidate_user_id", ASCENDING)], background=True)

    ensure_index(employee_documents_collection, [("employee_id", ASCENDING), ("document_type", ASCENDING)], background=True)
    ensure_index(hr_cases_collection, [("employee_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(learning_records_collection, [("employee_id", ASCENDING), ("status", ASCENDING), ("due_date", ASCENDING)], background=True)

    ensure_index(jobs_collection, [("status", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(jobs_collection, [("status", ASCENDING), ("open_until", ASCENDING)], background=True)
    ensure_index(jobs_collection, [("created_by", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(jobs_collection, [("viewer_user_ids", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(jobs_collection, [("controller_user_ids", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(applications_collection, [("job_id", ASCENDING), ("status", ASCENDING), ("final_score", DESCENDING)], background=True)
    ensure_index(applications_collection, [("job_id", ASCENDING), ("review_status", ASCENDING), ("final_score", DESCENDING)], background=True)
    ensure_index(applications_collection, [("source", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(applications_collection, [("candidate_email", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(applications_collection, [("candidate_user_id", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(resume_screening_collection, [("application_id", ASCENDING)], background=True)
    ensure_index(resume_screening_collection, [("job_id", ASCENDING), ("final_score", DESCENDING)], background=True)
    ensure_index(interview_sessions_collection, [("application_id", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(interview_sessions_collection, [("interviewer_user_id", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(interview_sessions_collection, [("panel_user_ids", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(interview_rooms_collection, [("room_code", ASCENDING)], unique=True, background=True)
    ensure_index(interview_messages_collection, [("room_code", ASCENDING), ("created_at", ASCENDING)], background=True)
    ensure_index(user_theme_collection, [("user_id", ASCENDING)], unique=True, background=True)
    ensure_index(hrms_messages_collection, [("conversation_key", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(hrms_messages_collection, [("participant_user_ids", ASCENDING), ("updated_at", DESCENDING)], background=True)
    ensure_index(hrms_messages_collection, [("sender_user_id", ASCENDING), ("receiver_user_id", ASCENDING), ("created_at", DESCENDING)], background=True)

    ensure_index(hrms_attendance_rules_collection, [("active", ASCENDING)], background=True)
    ensure_index(hrms_manager_assignments_collection, [("employee_user_id", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(hrms_manager_assignments_collection, [("manager_user_id", ASCENDING), ("status", ASCENDING)], background=True)
    ensure_index(hrms_attendance_reviews_collection, [("attendance_id", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(hrms_attendance_meetings_collection, [("employee_id", ASCENDING), ("meeting_date", DESCENDING)], background=True)
    ensure_index(hrms_attendance_meetings_collection, [("manager_user_id", ASCENDING), ("meeting_date", DESCENDING)], background=True)
    ensure_index(hrms_attendance_corrections_collection, [("employee_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(hrms_audit_logs_collection, [("actor_id", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(hrms_audit_logs_collection, [("target_user_id", ASCENDING), ("created_at", DESCENDING)], background=True)

    # Query patterns used by dashboards and high-traffic list pages.
    ensure_index(applications_collection, [("status", ASCENDING), ("created_at", DESCENDING)], background=True)
    ensure_index(applications_collection, [("job_id", ASCENDING), ("final_score", DESCENDING)], background=True)
    ensure_index(interview_messages_collection, [("room_code", ASCENDING), ("created_at", DESCENDING), ("_id", ASCENDING)], background=True)
    ensure_index(user_theme_collection, [("user_id", ASCENDING), ("updated_at", DESCENDING)], background=True)


ensure_performance_indexes()
