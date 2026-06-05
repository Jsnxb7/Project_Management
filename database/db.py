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


def ensure_performance_indexes():
    """Create safe non-destructive indexes for HRMS data access."""
    try:
        users_collection.create_index([("email", ASCENDING)], unique=True, background=True)
        users_collection.create_index([("is_active", ASCENDING), ("hrms_role", ASCENDING)], background=True)
        users_collection.create_index([("name", ASCENDING)], background=True)
        users_collection.create_index([("candidate_uid", ASCENDING)], sparse=True, background=True)

        notifications_collection.create_index([("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)], background=True)
        notifications_collection.create_index([("category", ASCENDING), ("created_at", DESCENDING)], background=True)
        activity_logs_collection.create_index([("scope", ASCENDING), ("created_at", DESCENDING)], background=True)
        activity_logs_collection.create_index([("actor_id", ASCENDING), ("created_at", DESCENDING)], background=True)

        employees_collection.create_index([("user_id", ASCENDING)], background=True)
        employees_collection.create_index([("employee_code", ASCENDING)], unique=True, sparse=True, background=True)
        employees_collection.create_index([("department", ASCENDING), ("employment_status", ASCENDING)], background=True)
        employees_collection.create_index([("manager_id", ASCENDING), ("employment_status", ASCENDING)], background=True)

        attendance_collection.create_index([("employee_id", ASCENDING), ("date", DESCENDING)], background=True)
        attendance_collection.create_index([("department", ASCENDING), ("date", DESCENDING)], background=True)
        attendance_collection.create_index([("status", ASCENDING), ("date", DESCENDING)], background=True)

        payroll_collection.create_index([("employee_id", ASCENDING), ("period", DESCENDING)], background=True)
        payroll_collection.create_index([("status", ASCENDING), ("period", DESCENDING)], background=True)

        performance_reviews_collection.create_index([("employee_id", ASCENDING), ("review_period", DESCENDING)], background=True)
        performance_reviews_collection.create_index([("manager_id", ASCENDING), ("status", ASCENDING)], background=True)

        leave_requests_collection.create_index([("employee_id", ASCENDING), ("status", ASCENDING), ("start_date", DESCENDING)], background=True)
        recruitment_candidates_collection.create_index([("status", ASCENDING), ("created_at", DESCENDING)], background=True)
        recruitment_candidates_collection.create_index([("job_title", ASCENDING), ("status", ASCENDING)], background=True)
        recruitment_candidates_collection.create_index([("candidate_email", ASCENDING)], background=True)
        recruitment_candidates_collection.create_index([("candidate_user_id", ASCENDING)], background=True)

        employee_documents_collection.create_index([("employee_id", ASCENDING), ("document_type", ASCENDING)], background=True)
        hr_cases_collection.create_index([("employee_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)], background=True)
        learning_records_collection.create_index([("employee_id", ASCENDING), ("status", ASCENDING), ("due_date", ASCENDING)], background=True)

        jobs_collection.create_index([("status", ASCENDING), ("created_at", DESCENDING)], background=True)
        jobs_collection.create_index([("status", ASCENDING), ("open_until", ASCENDING)], background=True)
        jobs_collection.create_index([("created_by", ASCENDING), ("status", ASCENDING)], background=True)
        jobs_collection.create_index([("viewer_user_ids", ASCENDING), ("status", ASCENDING)], background=True)
        jobs_collection.create_index([("controller_user_ids", ASCENDING), ("status", ASCENDING)], background=True)
        applications_collection.create_index([("job_id", ASCENDING), ("status", ASCENDING), ("final_score", DESCENDING)], background=True)
        applications_collection.create_index([("job_id", ASCENDING), ("review_status", ASCENDING), ("final_score", DESCENDING)], background=True)
        applications_collection.create_index([("source", ASCENDING), ("created_at", DESCENDING)], background=True)
        applications_collection.create_index([("candidate_email", ASCENDING), ("created_at", DESCENDING)], background=True)
        applications_collection.create_index([("candidate_user_id", ASCENDING), ("created_at", DESCENDING)], background=True)
        resume_screening_collection.create_index([("application_id", ASCENDING)], background=True)
        resume_screening_collection.create_index([("job_id", ASCENDING), ("final_score", DESCENDING)], background=True)
        interview_sessions_collection.create_index([("application_id", ASCENDING), ("status", ASCENDING)], background=True)
        interview_sessions_collection.create_index([("interviewer_user_id", ASCENDING), ("status", ASCENDING)], background=True)
        interview_sessions_collection.create_index([("panel_user_ids", ASCENDING), ("status", ASCENDING)], background=True)
        interview_rooms_collection.create_index([("room_code", ASCENDING)], unique=True, background=True)
        interview_messages_collection.create_index([("room_code", ASCENDING), ("created_at", ASCENDING)], background=True)
        user_theme_collection.create_index([("user_id", ASCENDING)], unique=True, background=True)

        # Query patterns used by dashboards and high-traffic list pages.
        applications_collection.create_index([("status", ASCENDING), ("created_at", DESCENDING)], background=True)
        applications_collection.create_index([("job_id", ASCENDING), ("final_score", DESCENDING)], background=True)
        interview_messages_collection.create_index([("room_code", ASCENDING), ("created_at", DESCENDING), ("_id", ASCENDING)], background=True)
        user_theme_collection.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)], background=True)
    except Exception as exc:
        print(f"[DB] Index creation skipped/failed: {exc}")


ensure_performance_indexes()
