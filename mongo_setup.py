"""
MongoDB Atlas Structure Setup for Team Task Manager
==================================================

Purpose:
- Connects securely to MongoDB Atlas using MONGO_URI from .env
- Creates required collections
- Adds indexes and constraints
- Optionally inserts one demo user/project/task if ENABLE_SEED=true

How to use:
1. Install dependencies:
   pip install pymongo python-dotenv Flask-Bcrypt dnspython

2. Create a .env file in your project root:
   MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/team_task_db?retryWrites=true&w=majority
   DB_NAME=team_task_db
   ENABLE_SEED=false

3. Run:
   python mongo_setup.py
"""

import os
from datetime import datetime, timezone, timedelta

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import CollectionInvalid, DuplicateKeyError
from flask_bcrypt import Bcrypt


load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "team_task_db")
ENABLE_SEED = os.getenv("ENABLE_SEED", "false").lower() == "true"

bcrypt = Bcrypt()


def get_db():
    if not MONGO_URI:
        raise RuntimeError(
            "MONGO_URI not found. Add it to your .env file before running this script."
        )

    client = MongoClient(MONGO_URI)
    client.admin.command("ping")
    print("[OK] Connected to MongoDB Atlas")

    return client[DB_NAME]


def create_collection(db, name):
    existing = db.list_collection_names()

    if name in existing:
        print(f"[SKIP] Collection already exists: {name}")
        return db[name]

    try:
        db.create_collection(name)
        print(f"[OK] Created collection: {name}")
    except CollectionInvalid:
        print(f"[SKIP] Collection already exists: {name}")

    return db[name]


def create_collections(db):
    collections = [
        "users",
        "projects",
        "tasks",
        "comments",
        "notifications",
        "activity_logs",
        "attachments",
        "organizations",
        "login_sessions",
        "subtasks",
        "user_org_memberships",
        "milestones",
    ]

    for name in collections:
        create_collection(db, name)


def create_indexes(db):
    # -----------------------------
    # USERS
    # -----------------------------
    db.users.create_index(
        [("email", ASCENDING)],
        unique=True,
        name="unique_user_email"
    )

    db.users.create_index(
        [("is_active", ASCENDING)],
        name="idx_user_active_status"
    )

    db.users.create_index(
        [("portal_role", ASCENDING)],
        name="idx_user_portal_role"
    )

    # -----------------------------
    # ORGANIZATIONS
    # -----------------------------
    db.organizations.create_index(
        [("name", ASCENDING)],
        name="idx_org_name"
    )
    db.organizations.create_index(
        [("members.user_id", ASCENDING)],
        name="idx_org_members_user_id"
    )
    db.organizations.create_index(
        [("status", ASCENDING)],
        name="idx_org_status"
    )

    # -----------------------------
    # USER ↔ ORGANIZATION MEMBERSHIPS
    # -----------------------------
    db.user_org_memberships.create_index(
        [("user_id", ASCENDING), ("organization_id", ASCENDING)],
        unique=True,
        name="unique_user_org_membership"
    )
    db.user_org_memberships.create_index(
        [("organization_id", ASCENDING), ("role", ASCENDING), ("status", ASCENDING)],
        name="idx_membership_org_role_status"
    )
    db.user_org_memberships.create_index(
        [("user_id", ASCENDING), ("status", ASCENDING)],
        name="idx_membership_user_status"
    )

    # -----------------------------
    # PROJECTS
    # -----------------------------
    db.projects.create_index(
        [("created_by", ASCENDING)],
        name="idx_project_created_by"
    )

    db.projects.create_index(
        [("organization_id", ASCENDING)],
        name="idx_project_organization_id"
    )

    db.projects.create_index(
        [("status", ASCENDING)],
        name="idx_project_status"
    )

    db.projects.create_index(
        [("members.user_id", ASCENDING)],
        name="idx_project_members_user_id"
    )

    db.projects.create_index(
        [("members.role", ASCENDING)],
        name="idx_project_members_role"
    )

    # -----------------------------
    # TASKS
    # -----------------------------
    db.tasks.create_index(
        [("project_id", ASCENDING)],
        name="idx_task_project_id"
    )
    db.tasks.create_index(
        [("organization_id", ASCENDING)],
        name="idx_task_organization_id"
    )

    db.tasks.create_index(
        [("assigned_to", ASCENDING)],
        name="idx_task_assigned_to"
    )

    db.tasks.create_index(
        [("created_by", ASCENDING)],
        name="idx_task_created_by"
    )

    db.tasks.create_index(
        [("status", ASCENDING)],
        name="idx_task_status"
    )

    db.tasks.create_index(
        [("priority", ASCENDING)],
        name="idx_task_priority"
    )

    db.tasks.create_index(
        [("due_date", ASCENDING)],
        name="idx_task_due_date"
    )

    db.tasks.create_index(
        [("project_id", ASCENDING), ("status", ASCENDING)],
        name="idx_task_project_status"
    )

    db.tasks.create_index(
        [("project_id", ASCENDING), ("assigned_to", ASCENDING)],
        name="idx_task_project_assignee"
    )

    db.tasks.create_index(
        [("milestone_id", ASCENDING)],
        name="idx_task_milestone_id"
    )

    db.tasks.create_index(
        [("is_deleted", ASCENDING)],
        name="idx_task_soft_delete"
    )

    # -----------------------------
    # MILESTONES
    # -----------------------------
    db.milestones.create_index(
        [("project_id", ASCENDING)],
        name="idx_milestone_project_id"
    )
    db.milestones.create_index(
        [("organization_id", ASCENDING)],
        name="idx_milestone_organization_id"
    )
    db.milestones.create_index(
        [("deadline", ASCENDING)],
        name="idx_milestone_deadline"
    )

    # -----------------------------
    # COMMENTS
    # -----------------------------
    db.comments.create_index(
        [("task_id", ASCENDING)],
        name="idx_comment_task_id"
    )

    db.comments.create_index(
        [("project_id", ASCENDING)],
        name="idx_comment_project_id"
    )

    db.comments.create_index(
        [("user_id", ASCENDING)],
        name="idx_comment_user_id"
    )

    db.comments.create_index(
        [("created_at", DESCENDING)],
        name="idx_comment_created_at"
    )

    # -----------------------------
    # NOTIFICATIONS
    # -----------------------------
    db.notifications.create_index(
        [("user_id", ASCENDING)],
        name="idx_notification_user_id"
    )

    db.notifications.create_index(
        [("is_read", ASCENDING)],
        name="idx_notification_read_status"
    )

    db.notifications.create_index(
        [("created_at", DESCENDING)],
        name="idx_notification_created_at"
    )

    # -----------------------------
    # ACTIVITY LOGS
    # -----------------------------
    db.activity_logs.create_index(
        [("project_id", ASCENDING)],
        name="idx_activity_project_id"
    )

    db.activity_logs.create_index(
        [("task_id", ASCENDING)],
        name="idx_activity_task_id"
    )

    db.activity_logs.create_index(
        [("user_id", ASCENDING)],
        name="idx_activity_user_id"
    )

    db.activity_logs.create_index(
        [("created_at", DESCENDING)],
        name="idx_activity_created_at"
    )

    # -----------------------------
    # ATTACHMENTS
    # -----------------------------
    db.attachments.create_index(
        [("task_id", ASCENDING)],
        name="idx_attachment_task_id"
    )

    db.attachments.create_index(
        [("uploaded_by", ASCENDING)],
        name="idx_attachment_uploaded_by"
    )

    print("[OK] Indexes created")


def seed_demo_data(db):
    """
    Optional seed data for testing.
    Enable by setting ENABLE_SEED=true in .env.
    """

    if not ENABLE_SEED:
        print("[SKIP] Demo seed disabled. Set ENABLE_SEED=true to add sample data.")
        return

    now = datetime.now(timezone.utc)

    demo_email = "admin@example.com"
    existing_user = db.users.find_one({"email": demo_email})

    if existing_user:
        print("[SKIP] Demo user already exists")
        admin_id = existing_user["_id"]
    else:
        admin_id = ObjectId()
        db.users.insert_one({
            "_id": admin_id,
            "name": "Demo Admin",
            "email": demo_email,
            "password_hash": bcrypt.generate_password_hash("Password123").decode("utf-8"),
            "profile_image": None,
            "portal_role": "Super User",
            "role": "Super User",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "last_login": None,
        })
        print("[OK] Demo user created")
        print("     Email: admin@example.com")
        print("     Password: Password123")

    existing_org = db.organizations.find_one({"name": "Demo Organization", "created_by": admin_id})
    if existing_org:
        print("[SKIP] Demo organization already exists")
        org_id = existing_org["_id"]
    else:
        org_id = ObjectId()
        db.organizations.insert_one({
            "_id": org_id,
            "name": "Demo Organization",
            "description": "Default organization for the demo project and demo members.",
            "visibility": "Internal",
            "status": "active",
            "created_by": admin_id,
            "members": [{"user_id": admin_id, "role": "Admin", "status": "active", "joined_at": now}],
            "created_at": now,
            "updated_at": now,
        })
        db.user_org_memberships.update_one(
            {"user_id": admin_id, "organization_id": org_id},
            {"$set": {"user_id": admin_id, "organization_id": org_id, "role": "Admin", "status": "active", "updated_at": now}, "$setOnInsert": {"joined_at": now}},
            upsert=True,
        )
        print("[OK] Demo organization created")

    existing_project = db.projects.find_one({"name": "Demo Project", "created_by": admin_id})

    if existing_project:
        print("[SKIP] Demo project already exists")
        project_id = existing_project["_id"]
    else:
        project_id = ObjectId()
        db.projects.insert_one({
            "_id": project_id,
            "name": "Demo Project",
            "description": "Sample project for testing the Team Task Manager.",
            "created_by": admin_id,
            "organization_id": org_id,
            "status": "active",
            "members": [
                {
                    "user_id": admin_id,
                    "role": "Admin",
                    "status": "active",
                    "joined_at": now,
                }
            ],
            "created_at": now,
            "updated_at": now,
        })
        print("[OK] Demo project created")

    existing_task = db.tasks.find_one({"title": "Create Login Page", "project_id": project_id})

    if existing_task:
        print("[SKIP] Demo task already exists")
    else:
        task_id = ObjectId()
        db.tasks.insert_one({
            "_id": task_id,
            "project_id": project_id,
            "organization_id": org_id,
            "title": "Create Login Page",
            "description": "Build the frontend login page and connect it to the Flask login API.",
            "assigned_to": admin_id,
            "created_by": admin_id,
            "due_date": now + timedelta(days=7),
            "priority": "High",
            "status": "To Do",
            "labels": ["Frontend", "Authentication"],
            "completed_at": None,
            "is_deleted": False,
            "created_at": now,
            "updated_at": now,
        })

        db.notifications.insert_one({
            "_id": ObjectId(),
            "user_id": admin_id,
            "message": "You were assigned a task: Create Login Page",
            "type": "task_assigned",
            "is_read": False,
            "created_at": now,
        })

        db.activity_logs.insert_one({
            "_id": ObjectId(),
            "project_id": project_id,
            "task_id": task_id,
            "user_id": admin_id,
            "action_type": "task_created",
            "description": 'Demo Admin created task "Create Login Page".',
            "created_at": now,
        })

        print("[OK] Demo task, notification, and activity log created")


def print_structure_summary(db):
    print("\nDatabase Structure Summary")
    print("==========================")

    for name in db.list_collection_names():
        count = db[name].count_documents({})
        print(f"- {name}: {count} document(s)")

    print("\nRecommended Collections:")
    print("- users")
    print("- organizations")
    print("- projects")
    print("- tasks")
    print("- comments")
    print("- notifications")
    print("- activity_logs")
    print("- attachments")
    print("- user_org_memberships")
    print("- milestones")


def main():
    try:
        db = get_db()
        print(f"[OK] Using database: {DB_NAME}")

        create_collections(db)
        create_indexes(db)
        seed_demo_data(db)
        print_structure_summary(db)

        print("\n[DONE] MongoDB Atlas structure setup completed successfully.")

    except DuplicateKeyError as e:
        print("[ERROR] Duplicate key error:")
        print(e)

    except Exception as e:
        print("[ERROR] Setup failed:")
        print(e)


if __name__ == "__main__":
    main()
