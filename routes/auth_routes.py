from flask import Blueprint, request, session
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from bson import ObjectId
from datetime import datetime, timezone

from app import bcrypt
from database.db import users_collection
from utils.response import ok, fail
from utils.validators import valid_email, valid_password

auth_bp = Blueprint("auth_bp", __name__)
# In-memory JWT denylist for assignment-level logout protection.
# For production, move this to Redis or MongoDB with expiry.
TOKEN_BLOCKLIST = set()


def user_public(user):
    return {
        "id": str(user["_id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "profile_image": user.get("profile_image"),
    }


@auth_bp.post("/signup")
def signup():
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

    existing = users_collection.find_one({"email": email})
    if existing:
        return fail("User already exists", 409)

    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    now = datetime.now(timezone.utc)

    result = users_collection.insert_one({
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "profile_image": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
    })

    return ok("User registered successfully", {"id": str(result.inserted_id)}, 201)


@auth_bp.post("/login")
def login():
    data = request.get_json() or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return fail("Email and password are required")

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
    session.clear()
    return ok("Logout successful")


@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        return fail("User not found", 404)
    return ok("Profile fetched", {"user": user_public(user)})
