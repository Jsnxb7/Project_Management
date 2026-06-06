from flask import Blueprint, request, session
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId
from datetime import datetime, timezone

from app import bcrypt
from database.db import copy_mongo_to_json, employees_collection, sync_json_to_mongo, users_collection
from utils.response import ok, fail
from utils.validators import valid_email, valid_password
from services.hrms_service import HRMS_ROLES, normalize_role, primary_super_user_id


auth_bp = Blueprint("auth_bp", __name__)
TOKEN_BLOCKLIST = set()
PORTAL_ROLES = HRMS_ROLES


def user_public(user):
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "profile_image": user.get("profile_image"),
        "portal_role": normalize_role(user.get("hrms_role") or user.get("portal_role") or user.get("role")),
        "hrms_role": normalize_role(user.get("hrms_role") or user.get("portal_role") or user.get("role")),
        "role": normalize_role(user.get("hrms_role") or user.get("portal_role") or user.get("role")),
        "is_active": user.get("is_active", True),
    }


@auth_bp.post("/signup")
def signup():
    """Public signup is enabled.
    The very first account becomes the Super User.
    All later public signups become regular Member portal users.
    """
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name:
        return fail("Name is required")
    if not valid_email(email):
        return fail("Valid email is required")
    if not valid_password(password):
        return fail("Password must be at least 8 characters and contain letters and numbers")
    if users_collection.find_one({"email": email}):
        return fail("An account with this email already exists", 409)

    existing_users = users_collection.count_documents({})
    portal_role = "Super User" if existing_users == 0 else "Employee"
    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    now = datetime.now(timezone.utc)

    result = users_collection.insert_one({
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "profile_image": None,
        "portal_role": portal_role,
        "hrms_role": portal_role,
        "role": portal_role,
        "is_active": True,
        "created_by": None,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
    })
    if portal_role != "Super User":
        manager_id = primary_super_user_id(exclude_user_id=result.inserted_id)
        manager_ids = [manager_id] if manager_id else []
        employees_collection.insert_one({
            "user_id": result.inserted_id,
            "employee_code": "",
            "name": name,
            "email": email,
            "phone": "",
            "department": "Unassigned",
            "designation": portal_role,
            "joining_date": now,
            "employment_status": "Active",
            "manager_id": manager_id,
            "manager_ids": manager_ids,
            "manager_status": "assigned" if manager_ids else "missing",
            "documents": [],
            "salary": {},
            "work_history": [],
            "created_by": None,
            "created_at": now,
            "updated_at": now,
        })

    message = "Super User account created successfully" if portal_role == "Super User" else "Account created successfully"
    return ok(message, {"id": str(result.inserted_id), "portal_role": portal_role}, 201)


@auth_bp.post("/login")
def login():
    data = request.get_json() or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return fail("Email and password are required")

    if users_collection.count_documents({}) == 0:
        try:
            copy_mongo_to_json()
        except Exception as exc:
            return fail(f"Unable to bootstrap local JSON database from Mongo Atlas: {exc}", 503)

    user = users_collection.find_one({"email": email, "is_active": True})
    if not user or not bcrypt.check_password_hash(user["password_hash"], password):
        return fail("Invalid email or password", 401)

    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc)}}
    )

    session.clear()
    session["user_id"] = str(user["_id"])
    session["user_name"] = user.get("name")
    session["portal_role"] = normalize_role(user.get("hrms_role") or user.get("portal_role") or user.get("role"))
    session["hrms_role"] = session["portal_role"]
    session.permanent = True

    token = create_access_token(identity=str(user["_id"]))
    return ok("Login successful", {
        "token": token,
        "user": user_public(user)
    })


@auth_bp.post("/logout")
@jwt_required(optional=True)
def logout():
    try:
        jti = get_jwt().get("jti")
        if jti:
            TOKEN_BLOCKLIST.add(jti)
    except Exception:
        pass
    try:
        sync_json_to_mongo()
    except Exception as exc:
        return fail(f"Logout backup to Mongo Atlas failed: {exc}", 503)
    session.clear()
    return ok("Logout successful")


@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = users_collection.find_one({"_id": ObjectId(user_id), "is_active": True})
    if not user:
        return fail("User not found", 404)
    return ok("Profile fetched", {"user": user_public(user)})
