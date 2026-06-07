from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import csv
import io
import json

from app import bcrypt
from database.db import users_collection, employees_collection, notifications_collection, user_theme_collection
from utils.response import ok, fail, warn
from utils.validators import valid_email, valid_password
from services.hrms_service import HRMS_ROLES, normalize_role, role_permissions, serialize_employee, to_object_id, user_role, primary_super_user_id


portal_bp = Blueprint("portal_bp", __name__)


def current_user():
    user_id = to_object_id(get_jwt_identity())
    return users_collection.find_one({"_id": user_id, "is_active": True}) if user_id else None


def can_manage_users(user):
    return role_permissions(user_role(user)).get("is_super_user")


def can_bulk_import_users(user):
    return role_permissions(user_role(user)).get("is_super_user")


def user_public(user):
    role = normalize_role(user.get("hrms_role") or user.get("portal_role") or user.get("role"))
    employee = employees_collection.find_one({"user_id": user["_id"]})
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "hrms_role": role,
        "portal_role": role,
        "role": role,
        "is_active": user.get("is_active", True),
        "employee": serialize_employee(employee),
        "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
        "last_login": user.get("last_login").isoformat() if user.get("last_login") else None,
    }


@portal_bp.get("/roles")
@jwt_required()
def portal_roles():
    return ok("HRMS roles fetched", {"roles": HRMS_ROLES, "permissions": {role: role_permissions(role) for role in HRMS_ROLES}})


@portal_bp.get("/users")
@jwt_required()
def list_users():
    me = current_user()
    if not can_manage_users(me):
        return warn("Warning: your HRMS role cannot view user management.")
    q = (request.args.get("q") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = max(1, min(int(request.args.get("limit", 25)), 100))
    except (TypeError, ValueError):
        limit = 25
    skip = (page - 1) * limit
    query = {}
    if q:
        query = {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"hrms_role": {"$regex": q, "$options": "i"}},
        ]}
    filtered_total = users_collection.count_documents(query)
    pages = max(1, (filtered_total + limit - 1) // limit)
    users = list(users_collection.find(query).sort("created_at", -1).skip(skip).limit(limit))
    return ok("HRMS users fetched", {
        "users": [user_public(user) for user in users],
        "meta": {
            "total_users": users_collection.count_documents({}),
            "filtered_total": filtered_total,
            "active_users": users_collection.count_documents({"is_active": True}),
            "roles": HRMS_ROLES,
            "page": page,
            "limit": limit,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1,
        },
    })


@portal_bp.post("/users")
@jwt_required()
def create_user():
    me = current_user()
    if not can_manage_users(me):
        return warn("Warning: your HRMS role cannot create users.")
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = normalize_role(data.get("hrms_role") or data.get("portal_role") or data.get("role"))
    if not name:
        return fail("Name is required")
    if not valid_email(email):
        return fail("Valid email is required")
    if not valid_password(password):
        return fail("Password must be at least 8 characters and contain letters and numbers")
    if role not in HRMS_ROLES:
        return fail("Invalid HRMS role")
    if users_collection.find_one({"email": email}):
        return fail("A user with this email already exists", 409)
    now = datetime.now(timezone.utc)
    result = users_collection.insert_one({
        "name": name,
        "email": email,
        "password_hash": bcrypt.generate_password_hash(password).decode("utf-8"),
        "profile_image": None,
        "hrms_role": role,
        "portal_role": role,
        "role": role,
        "is_active": True,
        "created_by": me["_id"],
        "created_at": now,
        "updated_at": now,
        "last_login": None,
    })
    maybe_create_employee(result.inserted_id, data, name, email, role, me["_id"])
    return ok("HRMS user created", {"id": str(result.inserted_id)}, 201)


@portal_bp.patch("/users/<user_id>")
@jwt_required()
def update_user(user_id):
    me = current_user()
    if not can_manage_users(me):
        return warn("Warning: your HRMS role cannot update users.")
    target_id = to_object_id(user_id)
    if not target_id:
        return fail("Invalid user id")
    data = request.get_json() or {}
    updates = {"updated_at": datetime.now(timezone.utc)}
    if "name" in data:
        updates["name"] = (data.get("name") or "").strip()
    if "hrms_role" in data or "portal_role" in data or "role" in data:
        role = normalize_role(data.get("hrms_role") or data.get("portal_role") or data.get("role"))
        if role not in HRMS_ROLES:
            return fail("Invalid HRMS role")
        updates.update({"hrms_role": role, "portal_role": role, "role": role})
    if "is_active" in data:
        if target_id == me["_id"] and data.get("is_active") is False:
            return fail("You cannot deactivate yourself")
        updates["is_active"] = bool(data.get("is_active"))
    result = users_collection.update_one({"_id": target_id}, {"$set": updates})
    if result.matched_count == 0:
        return fail("User not found", 404)
    employees_collection.update_one({"user_id": target_id}, {"$set": {k: v for k, v in {"name": updates.get("name"), "updated_at": updates["updated_at"]}.items() if v}})
    return ok("HRMS user updated")


@portal_bp.delete("/users/<user_id>")
@jwt_required()
def delete_user(user_id):
    me = current_user()
    if not can_manage_users(me):
        return warn("Warning: your HRMS role cannot delete users.")
    target_id = to_object_id(user_id)
    if not target_id:
        return fail("Invalid user id")
    if target_id == me["_id"]:
        return fail("You cannot delete yourself")
    target = users_collection.find_one({"_id": target_id})
    if not target:
        return fail("User not found", 404)
    target_role = user_role(target)
    if target_role == "Super User":
        other_super_users = users_collection.count_documents({
            "_id": {"$ne": target_id},
            "is_active": True,
            "$or": [
                {"hrms_role": "Super User"},
                {"portal_role": "Super User"},
                {"role": "Super User"},
            ],
        })
        if other_super_users == 0:
            return fail("You cannot delete the last active Super User")

    users_collection.delete_one({"_id": target_id})
    employees_collection.delete_many({"user_id": target_id})
    notifications_collection.delete_many({"user_id": target_id})
    user_theme_collection.delete_many({"user_id": target_id})
    return ok("User deleted successfully")


@portal_bp.post("/import/preview")
@jwt_required()
def preview_import():
    me = current_user()
    if not can_bulk_import_users(me):
        return warn("Warning: your HRMS role cannot import users.")
    upload = request.files.get("file")
    try:
        rows = parse_import_rows(upload, request.get_json(silent=True) if request.is_json else None)
    except ValueError as exc:
        return fail(str(exc))
    normalized = [normalize_import_row(row, index + 1) for index, row in enumerate(rows)]
    return ok("HRMS import preview ready", {
        "rows": normalized,
        "stats": {
            "total_rows": len(normalized),
            "valid_rows": sum(1 for row in normalized if row["valid"]),
            "invalid_rows": sum(1 for row in normalized if not row["valid"]),
        },
    })


@portal_bp.post("/import/commit")
@jwt_required()
def commit_import():
    me = current_user()
    if not can_bulk_import_users(me):
        return warn("Warning: your HRMS role cannot import users.")
    try:
        submitted = rows_from_json_payload(request.get_json(silent=True, force=False) or {"rows": []})
    except ValueError as exc:
        return fail(str(exc))
    created = 0
    skipped = []
    for index, row in enumerate(submitted):
        item = normalize_import_row(row, index + 1)
        if not item["valid"]:
            skipped.append({"row": item["row"], "email": item["email"], "reason": "; ".join(item["errors"])})
            continue
        if users_collection.find_one({"email": item["email"]}):
            skipped.append({"row": item["row"], "email": item["email"], "reason": "Email already exists"})
            continue
        now = datetime.now(timezone.utc)
        result = users_collection.insert_one({
            "name": item["name"],
            "email": item["email"],
            "password_hash": bcrypt.generate_password_hash(item["password"]).decode("utf-8"),
            "profile_image": None,
            "hrms_role": item["hrms_role"],
            "portal_role": item["hrms_role"],
            "role": item["hrms_role"],
            "is_active": True,
            "created_by": me["_id"],
            "created_at": now,
            "updated_at": now,
            "last_login": None,
            "imported_by_bulk": True,
        })
        maybe_create_employee(result.inserted_id, item, item["name"], item["email"], item["hrms_role"], me["_id"])
        created += 1
    return ok("HRMS user import completed", {"created": created, "skipped": skipped}, 201)


@portal_bp.get("/summary")
@jwt_required()
def portal_summary():
    me = current_user()
    if not can_manage_users(me):
        return warn("Warning: your HRMS role cannot view admin summary.")
    return ok("HRMS admin summary fetched", {
        "total_users": users_collection.count_documents({}),
        "active_users": users_collection.count_documents({"is_active": True}),
        "employees": employees_collection.count_documents({}),
    })


def parse_import_rows(upload=None, payload=None):
    if payload is not None:
        return rows_from_json_payload(payload)
    if not upload:
        raise ValueError("Upload a CSV or JSON file.")

    raw = upload.read().decode("utf-8-sig")
    filename = (upload.filename or "").lower()
    content_type = (upload.content_type or "").lower()
    if filename.endswith(".json") or "json" in content_type:
        return rows_from_json_payload(json.loads(raw))
    if filename.endswith(".csv") or "csv" in content_type or not filename:
        return list(csv.DictReader(io.StringIO(raw)))
    raise ValueError("Unsupported import file. Upload CSV or JSON.")


def rows_from_json_payload(payload):
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for key in ("users", "rows", "data"):
            if key in payload:
                rows = payload.get(key)
                break
    else:
        rows = None
    if not isinstance(rows, list):
        raise ValueError('JSON import must be an array, or an object with a "users", "rows", or "data" array.')
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("Every JSON import row must be an object.")
    return rows


def import_text(row, key, default=""):
    value = row.get(key, default)
    if value is None:
        return default
    return str(value).strip()


def normalize_import_row(row, index):
    name = import_text(row, "name") or import_text(row, "full_name")
    email = import_text(row, "email").lower()
    password = import_text(row, "password") or import_text(row, "temporary_password")
    role = normalize_role(import_text(row, "hrms_role") or import_text(row, "role") or "Employee")
    errors = []
    if not name:
        errors.append("Name is required.")
    if not valid_email(email):
        errors.append("Valid email is required.")
    if not valid_password(password):
        errors.append("Password must be at least 8 characters and contain letters and numbers.")
    if role not in HRMS_ROLES:
        errors.append("Invalid HRMS role.")
    return {
        "row": index,
        "name": name,
        "email": email,
        "password": password,
        "hrms_role": role,
        "employee_code": import_text(row, "employee_code"),
        "department": import_text(row, "department", "Unassigned") or "Unassigned",
        "designation": import_text(row, "designation", role) or role,
        "phone": import_text(row, "phone"),
        "valid": not errors,
        "errors": errors,
    }


def maybe_create_employee(user_id, data, name, email, role, actor_id):
    if employees_collection.find_one({"user_id": user_id}):
        return
    if data.get("create_employee_profile") is False:
        return
    now = datetime.now(timezone.utc)
    manager_id = to_object_id(data.get("manager_id")) or primary_super_user_id(exclude_user_id=user_id)
    manager_ids = [manager_id] if manager_id else []
    employees_collection.insert_one({
        "user_id": user_id,
        "employee_code": data.get("employee_code") or "",
        "name": name,
        "email": email,
        "phone": data.get("phone") or "",
        "department": data.get("department") or "Unassigned",
        "designation": data.get("designation") or role,
        "joining_date": now,
        "employment_status": "Active",
        "manager_id": manager_id,
        "manager_ids": manager_ids,
        "manager_status": "assigned" if manager_ids else "missing",
        "documents": [],
        "salary": {},
        "work_history": [],
        "created_by": actor_id,
        "created_at": now,
        "updated_at": now,
    })
