from bson import ObjectId
from database.db import projects_collection, users_collection
from services.relation_service import (
    to_object_id,
    get_org_role,
    get_active_org_ids_for_user,
    get_managed_org_ids_for_user,
    portal_role,
    is_super_user_id,
    get_project_role,
    can_manage_project,
    can_view_project,
    can_assign_task_to,
    active_project_member,
)


def get_user(user_id):
    user_obj_id = to_object_id(user_id)
    return users_collection.find_one({"_id": user_obj_id}) if user_obj_id else None


def get_project_for_user(project_id, user_id):
    project_obj_id = to_object_id(project_id)
    if not project_obj_id:
        return None

    project = projects_collection.find_one({"_id": project_obj_id, "status": "active"})
    if not project:
        return None
    return project if can_view_project(project, user_id) else None


def get_member_role(project, user_id):
    return get_project_role(project, user_id)


def is_project_admin(project, user_id):
    return can_manage_project(project, user_id)


def is_project_member(project, user_id):
    return get_project_role(project, user_id) in ["Super User", "Admin", "Org Head", "Team Lead", "Member"]


def user_in_project(project, target_user_id):
    if is_super_user_id(target_user_id):
        # Super User can manage globally, but task assignment still works best when they are explicit project members.
        return active_project_member(project, target_user_id) is not None
    return can_assign_task_to(project, target_user_id)
