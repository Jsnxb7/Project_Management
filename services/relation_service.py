from datetime import datetime, timezone
from bson import ObjectId

from database.db import organizations_collection, projects_collection, tasks_collection, users_collection
try:
    from database.db import user_org_memberships_collection
except Exception:  # Backward compatibility if db.py was not updated yet.
    user_org_memberships_collection = None

ORG_MANAGER_ROLES = ["Admin", "Org Head", "Team Lead"]
PROJECT_MANAGER_ROLES = ["Admin", "Org Head", "Team Lead"]


def to_object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except Exception:
        return None


def portal_role(user):
    return user.get("portal_role", user.get("role", "Member")) if user else "Member"


def is_super_user(user):
    return portal_role(user) == "Super User"


def is_super_user_id(user_id):
    user_obj_id = to_object_id(user_id)
    if not user_obj_id:
        return False
    return is_super_user(users_collection.find_one({"_id": user_obj_id}))


def active_org_member_from_doc(org, user_id):
    user_obj_id = to_object_id(user_id)
    if not org or not user_obj_id:
        return None
    for member in org.get("members", []):
        if member.get("user_id") == user_obj_id and member.get("status", "active") == "active":
            return member
    return None


def get_org_role(org_id, user_id):
    org_obj_id = to_object_id(org_id)
    user_obj_id = to_object_id(user_id)
    if not org_obj_id or not user_obj_id:
        return None

    if user_org_memberships_collection is not None:
        membership = user_org_memberships_collection.find_one({
            "organization_id": org_obj_id,
            "user_id": user_obj_id,
            "status": "active",
        })
        if membership:
            return membership.get("role", "Member")

    org = organizations_collection.find_one({"_id": org_obj_id})
    member = active_org_member_from_doc(org, user_obj_id)
    return member.get("role", "Member") if member else None


def get_active_org_ids_for_user(user_id):
    user_obj_id = to_object_id(user_id)
    if not user_obj_id:
        return []

    ids = []
    if user_org_memberships_collection is not None:
        ids = [m["organization_id"] for m in user_org_memberships_collection.find({
            "user_id": user_obj_id,
            "status": "active",
        }, {"organization_id": 1})]

    if not ids:
        ids = [o["_id"] for o in organizations_collection.find({
            "members": {"$elemMatch": {"user_id": user_obj_id, "status": "active"}},
            "status": {"$ne": "deleted"},
        }, {"_id": 1})]

    # Remove duplicates while preserving ObjectId values.
    seen = set()
    unique = []
    for oid in ids:
        key = str(oid)
        if key not in seen:
            seen.add(key)
            unique.append(oid)
    return unique


def get_managed_org_ids_for_user(user_id):
    user_obj_id = to_object_id(user_id)
    if not user_obj_id:
        return []
    if is_super_user_id(user_obj_id):
        return [o["_id"] for o in organizations_collection.find({"status": {"$ne": "deleted"}}, {"_id": 1})]

    managed = []
    for org_id in get_active_org_ids_for_user(user_obj_id):
        if get_org_role(org_id, user_obj_id) in ORG_MANAGER_ROLES:
            managed.append(org_id)
    return managed


def can_manage_org(org_id, user_id):
    if is_super_user_id(user_id):
        return True
    return get_org_role(org_id, user_id) in ORG_MANAGER_ROLES


def can_create_project_in_org(org_id, user_id):
    return can_manage_org(org_id, user_id)


def active_project_member(project, user_id):
    user_obj_id = to_object_id(user_id)
    if not project or not user_obj_id:
        return None
    for member in project.get("members", []):
        if member.get("user_id") == user_obj_id and member.get("status") == "active":
            return member
    return None


def get_project_role(project, user_id):
    if is_super_user_id(user_id):
        return "Super User"
    member = active_project_member(project, user_id)
    if member:
        return member.get("role", "Member")
    org_id = project.get("organization_id") if project else None
    org_role = get_org_role(org_id, user_id) if org_id else None
    if org_role in ORG_MANAGER_ROLES:
        return org_role
    return None


def can_view_project(project, user_id):
    if is_super_user_id(user_id):
        return True
    if active_project_member(project, user_id):
        return True
    org_role = get_org_role(project.get("organization_id"), user_id) if project and project.get("organization_id") else None
    return org_role in ORG_MANAGER_ROLES


def can_manage_project(project, user_id):
    role = get_project_role(project, user_id)
    return role in ["Super User", "Admin", "Org Head", "Team Lead"]


def can_assign_task_to(project, target_user_id):
    # Tasks must be assigned to an explicit active project member, not merely any org member.
    return active_project_member(project, target_user_id) is not None


def sync_user_org_membership(org_id, user_id, role="Member", status="active", added_by=None):
    org_obj_id = to_object_id(org_id)
    user_obj_id = to_object_id(user_id)
    added_by_id = to_object_id(added_by) if added_by else None
    if not org_obj_id or not user_obj_id:
        return False

    now = datetime.now(timezone.utc)
    org = organizations_collection.find_one({"_id": org_obj_id})
    if org:
        existing = any(m.get("user_id") == user_obj_id for m in org.get("members", []))
        if existing:
            organizations_collection.update_one(
                {"_id": org_obj_id, "members.user_id": user_obj_id},
                {"$set": {
                    "members.$.role": role,
                    "members.$.status": status,
                    "members.$.joined_at": now,
                    "updated_at": now,
                }}
            )
        else:
            organizations_collection.update_one(
                {"_id": org_obj_id},
                {"$push": {"members": {
                    "user_id": user_obj_id,
                    "role": role,
                    "status": status,
                    "joined_at": now,
                    "added_by": added_by_id,
                }}, "$set": {"updated_at": now}}
            )

    if user_org_memberships_collection is not None:
        user_org_memberships_collection.update_one(
            {"organization_id": org_obj_id, "user_id": user_obj_id},
            {"$set": {
                "organization_id": org_obj_id,
                "user_id": user_obj_id,
                "role": role,
                "status": status,
                "updated_at": now,
                "added_by": added_by_id,
            }, "$setOnInsert": {"joined_at": now}},
            upsert=True,
        )
    return True


def mark_user_org_membership_removed(org_id, user_id):
    org_obj_id = to_object_id(org_id)
    user_obj_id = to_object_id(user_id)
    if not org_obj_id or not user_obj_id:
        return False
    now = datetime.now(timezone.utc)
    organizations_collection.update_one(
        {"_id": org_obj_id},
        {"$set": {"members.$[m].status": "removed", "updated_at": now}},
        array_filters=[{"m.user_id": user_obj_id}],
    )
    if user_org_memberships_collection is not None:
        user_org_memberships_collection.update_one(
            {"organization_id": org_obj_id, "user_id": user_obj_id},
            {"$set": {"status": "removed", "updated_at": now}},
        )
    return True


def sync_existing_org_memberships():
    if user_org_memberships_collection is None:
        return 0
    synced = 0
    for org in organizations_collection.find({"status": {"$ne": "deleted"}}):
        for member in org.get("members", []):
            if member.get("user_id"):
                sync_user_org_membership(
                    org["_id"],
                    member.get("user_id"),
                    member.get("role", "Member"),
                    member.get("status", "active"),
                    member.get("added_by"),
                )
                synced += 1
    return synced
