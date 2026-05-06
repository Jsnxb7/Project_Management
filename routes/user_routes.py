from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone

from app import bcrypt
from database.db import users_collection, projects_collection, tasks_collection, activity_logs_collection
from utils.response import ok, fail
from utils.validators import valid_email, valid_password

user_bp = Blueprint("user_bp", __name__)


def public_user(user):
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "profile_image": user.get("profile_image"),
        "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
        "last_login": user["last_login"].isoformat() if user.get("last_login") else None,
    }


@user_bp.get("/profile")
@jwt_required()
def get_profile():
    user_id = ObjectId(get_jwt_identity())
    user = users_collection.find_one({"_id": user_id})

    if not user:
        return fail("User not found", 404)

    total_projects = projects_collection.count_documents({
        "status": "active",
        "members": {"$elemMatch": {"user_id": user_id, "status": "active"}}
    })

    assigned_tasks = tasks_collection.count_documents({
        "assigned_to": user_id,
        "is_deleted": False
    })

    completed_tasks = tasks_collection.count_documents({
        "assigned_to": user_id,
        "status": "Done",
        "is_deleted": False
    })

    recent_activity = list(
        activity_logs_collection
        .find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(10)
    )

    activities = [{
        "id": str(a["_id"]),
        "description": a.get("description"),
        "action_type": a.get("action_type"),
        "created_at": a["created_at"].isoformat() if a.get("created_at") else None,
    } for a in recent_activity]

    return ok("Profile fetched", {
        "user": public_user(user),
        "stats": {
            "total_projects": total_projects,
            "assigned_tasks": assigned_tasks,
            "completed_tasks": completed_tasks,
        },
        "recent_activity": activities
    })


@user_bp.put("/profile")
@jwt_required()
def update_profile():
    user_id = ObjectId(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not name:
        return fail("Name is required")

    updates = {
        "name": name,
        "updated_at": datetime.now(timezone.utc)
    }

    if email:
        if not valid_email(email):
            return fail("Valid email is required")

        existing = users_collection.find_one({"email": email, "_id": {"$ne": user_id}})
        if existing:
            return fail("Email is already used by another account", 409)

        updates["email"] = email

    users_collection.update_one({"_id": user_id}, {"$set": updates})
    return ok("Profile updated successfully")


@user_bp.put("/change-password")
@jwt_required()
def change_password():
    user_id = ObjectId(get_jwt_identity())
    data = request.get_json() or {}

    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    user = users_collection.find_one({"_id": user_id})
    if not user:
        return fail("User not found", 404)

    if not bcrypt.check_password_hash(user["password_hash"], current_password):
        return fail("Current password is incorrect", 401)

    if not valid_password(new_password):
        return fail("New password must be at least 8 characters and contain letters and numbers")

    password_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")

    users_collection.update_one(
        {"_id": user_id},
        {"$set": {
            "password_hash": password_hash,
            "updated_at": datetime.now(timezone.utc)
        }}
    )

    return ok("Password changed successfully")
