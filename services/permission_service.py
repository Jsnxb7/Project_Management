from bson import ObjectId
from database.db import projects_collection, tasks_collection


def to_object_id(value):
    try:
        return ObjectId(value)
    except Exception:
        return None


def get_project_for_user(project_id, user_id):
    project_obj_id = to_object_id(project_id)
    user_obj_id = to_object_id(user_id)

    if not project_obj_id or not user_obj_id:
        return None

    return projects_collection.find_one({
        "_id": project_obj_id,
        "status": "active",
        "members": {
            "$elemMatch": {
                "user_id": user_obj_id,
                "status": "active"
            }
        }
    })


def get_member_role(project, user_id):
    user_obj_id = to_object_id(user_id)

    for member in project.get("members", []):
        if member.get("user_id") == user_obj_id and member.get("status") == "active":
            return member.get("role")

    return None


def is_project_admin(project, user_id):
    return get_member_role(project, user_id) == "Admin"


def is_project_member(project, user_id):
    return get_member_role(project, user_id) in ["Admin", "Member"]


def user_in_project(project, target_user_id):
    target_obj_id = to_object_id(target_user_id)

    if not target_obj_id:
        return False

    return any(
        member.get("user_id") == target_obj_id and member.get("status") == "active"
        for member in project.get("members", [])
    )
