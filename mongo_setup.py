"""
MongoDB Atlas setup for PeopleOps HRMS.

Creates HRMS indexes and, when ENABLE_SEED=true, inserts a Management Admin
user plus a small employee/attendance/payroll/performance sample.
"""

from datetime import datetime, timezone
import os

from bson import ObjectId
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from pymongo import ASCENDING, DESCENDING, MongoClient


load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "hrms_db")
ENABLE_SEED = os.getenv("ENABLE_SEED", "false").lower() == "true"

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing. Create a .env file using .env.example.")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
bcrypt = Bcrypt()


def create_indexes():
    db.users.create_index([("email", ASCENDING)], unique=True, background=True)
    db.users.create_index([("is_active", ASCENDING), ("hrms_role", ASCENDING)], background=True)
    db.employees.create_index([("user_id", ASCENDING)], background=True)
    db.employees.create_index([("employee_code", ASCENDING)], background=True)
    db.employees.create_index([("department", ASCENDING), ("employment_status", ASCENDING)], background=True)
    db.employees.create_index([("manager_id", ASCENDING), ("employment_status", ASCENDING)], background=True)
    db.attendance.create_index([("employee_id", ASCENDING), ("date", DESCENDING)], background=True)
    db.payroll.create_index([("employee_id", ASCENDING), ("period", DESCENDING)], background=True)
    db.performance_reviews.create_index([("employee_id", ASCENDING), ("review_period", DESCENDING)], background=True)
    db.leave_requests.create_index([("employee_id", ASCENDING), ("status", ASCENDING), ("start_date", DESCENDING)], background=True)
    db.recruitment_candidates.create_index([("status", ASCENDING), ("created_at", DESCENDING)], background=True)
    db.employee_documents.create_index([("employee_id", ASCENDING), ("document_type", ASCENDING)], background=True)
    db.hr_cases.create_index([("employee_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)], background=True)
    db.learning_records.create_index([("employee_id", ASCENDING), ("status", ASCENDING), ("due_date", ASCENDING)], background=True)
    db.notifications.create_index([("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)], background=True)
    db.activity_logs.create_index([("scope", ASCENDING), ("created_at", DESCENDING)], background=True)
    print("[OK] HRMS indexes ready")


def seed_demo():
    now = datetime.now(timezone.utc)
    email = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
    password = os.getenv("SEED_ADMIN_PASSWORD", "AdminPass123")
    existing = db.users.find_one({"email": email})
    if existing:
        admin_id = existing["_id"]
        print("[SKIP] Demo Management Admin already exists")
    else:
        admin_id = db.users.insert_one({
            "name": "Management Admin",
            "email": email,
            "password_hash": bcrypt.generate_password_hash(password).decode("utf-8"),
            "profile_image": None,
            "hrms_role": "Management Admin",
            "portal_role": "Management Admin",
            "role": "Management Admin",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "last_login": None,
        }).inserted_id
        print("[OK] Demo Management Admin created")

    employee = db.employees.find_one({"user_id": admin_id})
    if not employee:
        employee_id = db.employees.insert_one({
            "user_id": admin_id,
            "employee_code": "HRMS-ADMIN",
            "name": "Management Admin",
            "email": email,
            "phone": "",
            "department": "Management",
            "designation": "Management Admin",
            "joining_date": now,
            "employment_status": "Active",
            "manager_id": None,
            "documents": [],
            "salary": {"basic": 100000, "allowances": 25000},
            "work_history": [],
            "created_at": now,
            "updated_at": now,
        }).inserted_id
        print("[OK] Demo employee profile created")
    else:
        employee_id = employee["_id"]
        print("[SKIP] Demo employee profile already exists")

    db.attendance.update_one(
        {"employee_id": employee_id, "date": now.date().isoformat()},
        {"$setOnInsert": {"employee_id": employee_id, "date": now, "status": "Present", "working_hours": 8, "late_mark": False, "created_at": now}},
        upsert=True,
    )
    db.payroll.update_one(
        {"employee_id": employee_id, "period": now.strftime("%Y-%m")},
        {"$setOnInsert": {"employee_id": employee_id, "period": now.strftime("%Y-%m"), "basic_salary": 100000, "allowances": 25000, "deductions": 0, "tax": 10000, "net_salary": 115000, "status": "Approved", "created_at": now}},
        upsert=True,
    )
    db.performance_reviews.update_one(
        {"employee_id": employee_id, "review_period": now.strftime("%Y")},
        {"$setOnInsert": {"employee_id": employee_id, "manager_id": admin_id, "review_period": now.strftime("%Y"), "manager_rating": 4.5, "kpis": [], "goals": [], "feedback": "Demo HRMS review.", "promotion_recommendation": False, "status": "Completed", "created_at": now}},
        upsert=True,
    )
    print("[OK] Demo HRMS records ready")


if __name__ == "__main__":
    create_indexes()
    if ENABLE_SEED:
        seed_demo()
    print(f"[DONE] PeopleOps HRMS database setup complete for {DB_NAME}")
