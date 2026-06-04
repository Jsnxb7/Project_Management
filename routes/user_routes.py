from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import bcrypt
from database.db import users_collection, employees_collection, attendance_collection, payroll_collection, performance_reviews_collection
from utils.response import ok, fail
from utils.validators import valid_email, valid_password
from services.hrms_service import current_employee_for_user, normalize_role, serialize_employee, to_object_id


user_bp = Blueprint("user_bp", __name__)


def public_user(user):
    role = normalize_role(user.get("hrms_role") or user.get("portal_role") or user.get("role"))
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "profile_image": user.get("profile_image"),
        "hrms_role": role,
        "portal_role": role,
        "role": role,
        "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
        "last_login": user["last_login"].isoformat() if user.get("last_login") else None,
    }


@user_bp.get("/profile")
@jwt_required()
def get_profile():
    user_id = to_object_id(get_jwt_identity())
    user = users_collection.find_one({"_id": user_id})
    if not user:
        return fail("User not found", 404)

    employee = current_employee_for_user(user_id)
    employee_id = employee["_id"] if employee else None
    query = {"employee_id": employee_id} if employee_id else {"employee_id": None}
    return ok("Profile fetched", {
        "user": public_user(user),
        "employee": serialize_employee(employee),
        "stats": {
            "attendance_logs": attendance_collection.count_documents(query),
            "payslips": payroll_collection.count_documents(query),
            "performance_reviews": performance_reviews_collection.count_documents(query),
        },
        "recent_activity": [],
    })


@user_bp.put("/profile")
@jwt_required()
def update_profile():
    user_id = to_object_id(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not name:
        return fail("Name is required")
    updates = {"name": name, "updated_at": datetime.now(timezone.utc)}
    if email:
        if not valid_email(email):
            return fail("Valid email is required")
        if users_collection.find_one({"email": email, "_id": {"$ne": user_id}}):
            return fail("Email is already used by another account", 409)
        updates["email"] = email
    users_collection.update_one({"_id": user_id}, {"$set": updates})
    employee_updates = {"name": name, "updated_at": datetime.now(timezone.utc)}
    if email:
        employee_updates["email"] = email
    employees_collection.update_one({"user_id": user_id}, {"$set": employee_updates})
    return ok("Profile updated successfully")


@user_bp.put("/change-password")
@jwt_required()
def change_password():
    user_id = to_object_id(get_jwt_identity())
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
    users_collection.update_one(
        {"_id": user_id},
        {"$set": {"password_hash": bcrypt.generate_password_hash(new_password).decode("utf-8"), "updated_at": datetime.now(timezone.utc)}}
    )
    return ok("Password changed successfully")
