import os
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from werkzeug.utils import secure_filename

from database.db import attachments_collection, tasks_collection
from utils.response import ok, fail, warn
from services.permission_service import get_project_for_user, is_project_admin, to_object_id
from services.activity_service import log_activity
from services.notification_service import create_notification

attachment_bp = Blueprint("attachment_bp", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "doc", "docx", "txt", "zip"}
MAX_FILE_SIZE = 8 * 1024 * 1024


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def attachment_public(attachment):
    return {
        "id": str(attachment["_id"]),
        "task_id": str(attachment["task_id"]),
        "project_id": str(attachment["project_id"]),
        "uploaded_by": str(attachment["uploaded_by"]),
        "file_name": attachment.get("file_name"),
        "stored_name": attachment.get("stored_name"),
        "file_url": attachment.get("file_url"),
        "file_type": attachment.get("file_type"),
        "file_size": attachment.get("file_size"),
        "uploaded_at": attachment["uploaded_at"].isoformat() if attachment.get("uploaded_at") else None,
    }


def can_access_task(task, user_id):
    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return None, False, False

    is_admin = is_project_admin(project, user_id)
    is_assigned = task.get("assigned_to") == ObjectId(user_id)
    return project, is_admin, is_assigned


@attachment_bp.post("/tasks/<task_id>/attachments")
@jwt_required()
def upload_attachment(task_id):
    user_id = get_jwt_identity()

    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")

    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)

    project, is_admin, is_assigned = can_access_task(task, user_id)
    if not project:
        return warn("Warning: you do not have permission to access this item.")

    if not is_admin and not is_assigned:
        return warn("Warning: members can upload files only to their assigned tasks.")

    if "file" not in request.files:
        return fail("No file uploaded")

    file = request.files["file"]

    if not file or not file.filename:
        return fail("No file selected")

    if not allowed_file(file.filename):
        return fail("File type not allowed")

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        return fail("File size must be less than 8 MB")

    original_name = secure_filename(file.filename)
    ext = original_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"

    upload_dir = os.path.join(current_app.root_path, current_app.config.get("UPLOAD_FOLDER", "static/uploads"))
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, stored_name)
    file.save(file_path)

    file_url = url_for("static", filename=f"uploads/{stored_name}")

    now = datetime.now(timezone.utc)
    result = attachments_collection.insert_one({
        "task_id": task_obj_id,
        "project_id": task["project_id"],
        "organization_id": task.get("organization_id"),
        "uploaded_by": ObjectId(user_id),
        "file_name": original_name,
        "stored_name": stored_name,
        "file_url": file_url,
        "file_type": ext,
        "file_size": file_size,
        "uploaded_at": now,
    })

    log_activity(
        task["project_id"],
        user_id,
        "file_uploaded",
        f'File "{original_name}" was uploaded to task "{task.get("title", "Untitled Task")}".',
        task_obj_id
    )

    assigned_to = task.get("assigned_to")
    if assigned_to and str(assigned_to) != user_id:
        create_notification(
            assigned_to,
            f'New file uploaded on task "{task.get("title", "Untitled Task")}".',
            "file_uploaded",
            task["project_id"],
            task_obj_id
        )

    return ok("File uploaded successfully", {"id": str(result.inserted_id), "file_url": file_url}, 201)


@attachment_bp.get("/tasks/<task_id>/attachments")
@jwt_required()
def get_attachments(task_id):
    user_id = get_jwt_identity()

    task_obj_id = to_object_id(task_id)
    if not task_obj_id:
        return fail("Invalid task id")

    task = tasks_collection.find_one({"_id": task_obj_id, "is_deleted": False})
    if not task:
        return fail("Task not found", 404)

    project = get_project_for_user(str(task["project_id"]), user_id)
    if not project:
        return warn("Warning: you do not have permission to access this item.")

    attachments = list(attachments_collection.find({"task_id": task_obj_id}).sort("uploaded_at", -1))
    return ok("Attachments fetched", {"attachments": [attachment_public(a) for a in attachments]})


@attachment_bp.delete("/attachments/<attachment_id>")
@jwt_required()
def delete_attachment(attachment_id):
    user_id = get_jwt_identity()

    attachment_obj_id = to_object_id(attachment_id)
    if not attachment_obj_id:
        return fail("Invalid attachment id")

    attachment = attachments_collection.find_one({"_id": attachment_obj_id})
    if not attachment:
        return fail("Attachment not found", 404)

    task = tasks_collection.find_one({"_id": attachment["task_id"], "is_deleted": False})
    if not task:
        return fail("Task not found", 404)

    project = get_project_for_user(str(attachment["project_id"]), user_id)
    if not project:
        return warn("Warning: you do not have permission to access this item.")

    can_delete = attachment["uploaded_by"] == ObjectId(user_id) or is_project_admin(project, user_id)
    if not can_delete:
        return warn("Warning: only the uploader, Project Admin, Org Head, Team Lead, or Super User can delete this attachment.")

    upload_dir = os.path.join(current_app.root_path, current_app.config.get("UPLOAD_FOLDER", "static/uploads"))
    file_path = os.path.join(upload_dir, attachment.get("stored_name", ""))

    if os.path.exists(file_path):
        os.remove(file_path)

    attachments_collection.delete_one({"_id": attachment_obj_id})

    log_activity(
        attachment["project_id"],
        user_id,
        "file_deleted",
        f'File "{attachment.get("file_name", "file")}" was deleted.',
        attachment["task_id"]
    )

    return ok("Attachment deleted successfully")
