from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone

from app import bcrypt
from database.db import users_collection, organizations_collection
from utils.response import ok, fail, warn
from utils.validators import valid_email, valid_password
from services.relation_service import sync_user_org_membership

portal_bp = Blueprint("portal_bp", __name__)
PORTAL_ROLES = ["Super User", "Admin", "Org Head", "Team Lead", "Member"]


def current_user():
    uid = get_jwt_identity()
    return users_collection.find_one({"_id": ObjectId(uid)}) if uid else None


def is_super_user(user):
    return user and user.get("portal_role", user.get("role")) == "Super User"


def oid(value):
    try:
        return ObjectId(value)
    except Exception:
        return None


def user_orgs(user_id):
    orgs = list(organizations_collection.find({
        "status": {"$ne": "deleted"},
        "members": {"$elemMatch": {"user_id": user_id, "status": "active"}}
    }, {"name": 1, "members": 1}).sort("name", 1))
    data = []
    for org in orgs:
        role = next((m.get("role") for m in org.get("members", []) if m.get("user_id") == user_id and m.get("status", "active") == "active"), "Member")
        data.append({"id": str(org["_id"]), "name": org.get("name"), "role": role})
    return data


def add_user_to_org(org_id, user_id, role="Member"):
    org_obj_id = oid(org_id)
    if not org_obj_id:
        return None, "Warning: choose a valid organization."
    org = organizations_collection.find_one({"_id": org_obj_id, "status": {"$ne": "deleted"}})
    if not org:
        return None, "Warning: selected organization was not found."
    if any(m.get("user_id") == user_id and m.get("status", "active") == "active" for m in org.get("members", [])):
        return org, "Warning: this user already belongs to the selected organization."
    sync_user_org_membership(org_obj_id, user_id, role, "active")
    return org, None


def user_public(user):
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "portal_role": user.get("portal_role", user.get("role", "Member")),
        "role": user.get("portal_role", user.get("role", "Member")),
        "is_active": user.get("is_active", True),
        "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
        "last_login": user.get("last_login").isoformat() if user.get("last_login") else None,
        "organizations": user_orgs(user["_id"]),
        "relation_warnings": [] if user_orgs(user["_id"]) else ["This user is not assigned to any organization yet."],
    }


@portal_bp.get("/users")
@jwt_required()
def list_users():
    me = current_user()
    if not is_super_user(me):
        return warn("Warning: only the Super User can view portal users.")

    users = list(users_collection.find({}).sort("created_at", -1))
    return ok("Portal users fetched", {"users": [user_public(u) for u in users]})


@portal_bp.post("/users")
@jwt_required()
def create_user():
    me = current_user()
    if not is_super_user(me):
        return warn("Warning: only the Super User can create portal users.")

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    portal_role = data.get("portal_role") or data.get("role") or "Member"
    organization_id = data.get("organization_id")
    org_role = data.get("org_role") or "Member"

    if portal_role not in PORTAL_ROLES:
        return fail("Invalid portal role")
    if portal_role == "Super User" and users_collection.find_one({"portal_role": "Super User"}):
        return fail("A Super User already exists")
    if not name:
        return fail("Name is required")
    if not valid_email(email):
        return fail("Valid email is required")
    if not valid_password(password):
        return fail("Password must be at least 8 characters and contain letters and numbers")
    if users_collection.find_one({"email": email}):
        return fail("A user with this email already exists", 409)
    if org_role not in ["Admin", "Org Head", "Team Lead", "Member"]:
        return fail("Invalid organization role")

    now = datetime.now(timezone.utc)
    result = users_collection.insert_one({
        "name": name,
        "email": email,
        "password_hash": bcrypt.generate_password_hash(password).decode("utf-8"),
        "profile_image": None,
        "portal_role": portal_role,
        "role": portal_role,
        "is_active": True,
        "created_by": me["_id"],
        "created_at": now,
        "updated_at": now,
        "last_login": None,
    })
    warning_message = None
    if organization_id:
        _, warning_message = add_user_to_org(organization_id, result.inserted_id, org_role)
    if warning_message:
        return warn(f"Portal user was created, but organization assignment needs attention. {warning_message}", {"id": str(result.inserted_id)})
    return ok("Portal user created successfully", {"id": str(result.inserted_id)}, 201)


@portal_bp.patch("/users/<user_id>")
@jwt_required()
def update_user(user_id):
    me = current_user()
    if not is_super_user(me):
        return warn("Warning: only the Super User can update portal users.")

    try:
        target_id = ObjectId(user_id)
    except Exception:
        return fail("Invalid user id")

    data = request.get_json() or {}
    update = {"updated_at": datetime.now(timezone.utc)}

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return fail("Name cannot be empty")
        update["name"] = name

    if "portal_role" in data or "role" in data:
        role = data.get("portal_role") or data.get("role")
        if role not in PORTAL_ROLES:
            return fail("Invalid portal role")
        if role == "Super User":
            existing = users_collection.find_one({"portal_role": "Super User", "_id": {"$ne": target_id}})
            if existing:
                return fail("Only one Super User is allowed")
        update["portal_role"] = role
        update["role"] = role

    if "is_active" in data:
        if target_id == me["_id"] and data.get("is_active") is False:
            return fail("You cannot deactivate yourself")
        update["is_active"] = bool(data.get("is_active"))

    result = users_collection.update_one({"_id": target_id}, {"$set": update})
    if result.matched_count == 0:
        return fail("User not found", 404)
    return ok("Portal user updated")


@portal_bp.post("/users/<user_id>/organizations")
@jwt_required()
def assign_user_to_org(user_id):
    me = current_user()
    if not is_super_user(me):
        return warn("Warning: only the Super User can assign users from the portal user panel. Org Heads can add users from their organization page.")

    target_id = oid(user_id)
    if not target_id:
        return warn("Warning: choose a valid portal user.")
    target = users_collection.find_one({"_id": target_id, "is_active": True})
    if not target:
        return warn("Warning: portal user not found or inactive.")

    data = request.get_json() or {}
    role = data.get("role") or "Member"
    if role not in ["Admin", "Org Head", "Team Lead", "Member"]:
        return fail("Invalid organization role")

    org, warning_message = add_user_to_org(data.get("organization_id"), target_id, role)
    if warning_message:
        return warn(warning_message)
    return ok(f'{target.get("name", "User")} added to {org.get("name", "organization")}')


@portal_bp.get("/summary")
@jwt_required()
def portal_summary():
    me = current_user()
    if not is_super_user(me):
        return warn("Warning: only the Super User can view portal summary.")
    return ok("Portal summary fetched", {
        "total_users": users_collection.count_documents({}),
        "active_users": users_collection.count_documents({"is_active": True}),
        "organizations": organizations_collection.count_documents({"status": {"$ne": "deleted"}}),
    })
