from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime, timezone
import re

from database.db import organizations_collection, users_collection, projects_collection, activity_logs_collection, teams_collection
from utils.response import ok, fail, warn
from services.relation_service import sync_user_org_membership, mark_user_org_membership_removed

organization_bp = Blueprint("organization_bp", __name__)
ORG_ROLES = ["Admin", "Org Head", "Team Lead", "Member"]
MANAGER_ROLES = ["Super User", "Admin", "Org Head"]


def oid(value):
    try:
        return ObjectId(value)
    except Exception:
        return None


def current_user():
    uid = get_jwt_identity()
    return users_collection.find_one({"_id": ObjectId(uid)}) if uid else None


def portal_role(user):
    return user.get("portal_role", user.get("role", "Member")) if user else "Member"


def is_super_user(user):
    return portal_role(user) == "Super User"


def org_role(org, user_id):
    user_obj_id = oid(user_id)
    if not user_obj_id:
        return None
    for m in org.get("members", []):
        if m.get("user_id") == user_obj_id and m.get("status", "active") == "active":
            return m.get("role")
    return None


def active_org_managers(org, exclude_user_id=None):
    exclude = oid(exclude_user_id) if exclude_user_id else None
    return [
        m for m in org.get("members", [])
        if m.get("status", "active") == "active"
        and m.get("role") in ["Admin", "Org Head"]
        and m.get("user_id") != exclude
    ]


def active_projects_for_org_member(org_obj_id, user_obj_id):
    return list(projects_collection.find({
        "organization_id": org_obj_id,
        "status": "active",
        "members": {"$elemMatch": {"user_id": user_obj_id, "status": {"$in": ["active", "pending"]}}}
    }, {"name": 1}).limit(8))


def can_manage_org(user, org=None):
    if is_super_user(user):
        return True
    if not org:
        return portal_role(user) in ["Admin"]
    return org_role(org, user["_id"]) in ["Admin", "Org Head"]


def active_members(org):
    return [m for m in org.get("members", []) if m.get("status", "active") == "active" and m.get("user_id")]


def user_map_for_ids(user_ids):
    ids = list({uid for uid in user_ids if uid})
    if not ids:
        return {}
    return {u["_id"]: u for u in users_collection.find({"_id": {"$in": ids}}, {"name": 1, "email": 1, "portal_role": 1, "is_active": 1})}


def project_count_map_for_org(org_obj_id, user_ids):
    ids = list({uid for uid in user_ids if uid})
    counts = {uid: 0 for uid in ids}
    if not ids:
        return counts
    # One query for every visible member instead of one count query per member.
    projects = projects_collection.find({
        "organization_id": org_obj_id,
        "status": "active",
        "members": {"$elemMatch": {"user_id": {"$in": ids}, "status": {"$in": ["active", "pending"]}}}
    }, {"members.user_id": 1, "members.status": 1})
    wanted = set(ids)
    for project in projects:
        seen = set()
        for member in project.get("members", []):
            uid = member.get("user_id")
            if uid in wanted and uid not in seen and member.get("status") in ["active", "pending"]:
                counts[uid] = counts.get(uid, 0) + 1
                seen.add(uid)
    return counts


def member_public(member, user_lookup=None, project_counts=None):
    user_lookup = user_lookup or {}
    project_counts = project_counts or {}
    user_id = member.get("user_id")
    user = user_lookup.get(user_id)
    return {
        "user_id": str(user_id),
        "name": user.get("name") if user else "Unknown User",
        "email": user.get("email") if user else "",
        "role": member.get("role", "Member"),
        "status": member.get("status", "active"),
        "joined_at": member.get("joined_at").isoformat() if member.get("joined_at") else None,
        "project_count": project_counts.get(user_id, 0),
    }


def org_summary(org, user=None, project_count=None, team_count=None):
    members = active_members(org)
    return {
        "id": str(org["_id"]),
        "name": org.get("name"),
        "description": org.get("description", ""),
        "status": org.get("status", "active"),
        "visibility": org.get("visibility", "Private"),
        "created_by": str(org.get("created_by")) if org.get("created_by") else None,
        # Important: list pages return counts only. Full members are loaded only on the detail page.
        "member_count": len(members),
        "project_count": project_count,
        "team_count": team_count,
        "user_role": "Super User" if user and is_super_user(user) else (org_role(org, user["_id"]) if user else None),
        "created_at": org.get("created_at").isoformat() if org.get("created_at") else None,
        "updated_at": org.get("updated_at").isoformat() if org.get("updated_at") else None,
    }


def org_detail_payload(org, user=None, members_limit=25, members_q=""):
    members = active_members(org)
    total_members = len(members)
    q = (members_q or "").strip().lower()
    member_ids = [m.get("user_id") for m in members]
    lookup = user_map_for_ids(member_ids)

    if q:
        def matches(member):
            u = lookup.get(member.get("user_id"), {})
            hay = f"{u.get('name', '')} {u.get('email', '')} {member.get('role', '')}".lower()
            return q in hay
        members = [m for m in members if matches(m)]

    filtered_members = len(members)
    members = members[:members_limit]
    visible_ids = [m.get("user_id") for m in members]
    counts = project_count_map_for_org(org["_id"], visible_ids)

    projects = list(projects_collection.find(
        {"organization_id": org["_id"], "status": "active"},
        {"name": 1, "workflow_status": 1, "priority": 1, "updated_at": 1}
    ).sort("updated_at", -1).limit(50))

    data = org_summary(
        org,
        user,
        project_count=projects_collection.count_documents({"organization_id": org["_id"], "status": "active"}),
        team_count=teams_collection.count_documents({"organization_id": org["_id"], "status": {"$ne": "deleted"}}),
    )
    data["members"] = [member_public(m, lookup, counts) for m in members]
    data["members_visible"] = len(data["members"])
    data["members_filtered"] = filtered_members
    data["members_total"] = total_members
    data["members_limit"] = members_limit
    data["projects"] = [{"id": str(p["_id"]), "name": p.get("name"), "workflow_status": p.get("workflow_status", "Active"), "priority": p.get("priority", "Medium")} for p in projects]
    data["projects_visible"] = len(projects)
    return data


@organization_bp.get("")
@jwt_required()
def list_orgs():
    me = current_user()
    q = (request.args.get("q") or "").strip()
    limit = min(max(int(request.args.get("limit", 100) or 100), 1), 200)
    query = {"status": {"$ne": "deleted"}}
    if q:
        query["$or"] = [
            {"name": {"$regex": re.escape(q), "$options": "i"}},
            {"description": {"$regex": re.escape(q), "$options": "i"}},
        ]
    if not is_super_user(me):
        query["members"] = {"$elemMatch": {"user_id": me["_id"], "status": "active"}}
    orgs = list(organizations_collection.find(query, {"members": 1, "name": 1, "description": 1, "status": 1, "visibility": 1, "created_by": 1, "created_at": 1, "updated_at": 1}).sort("updated_at", -1).limit(limit))
    org_ids = [o["_id"] for o in orgs]
    project_counts = {o["_id"]: 0 for o in orgs}
    team_counts = {o["_id"]: 0 for o in orgs}
    if org_ids:
        for row in projects_collection.aggregate([
            {"$match": {"organization_id": {"$in": org_ids}, "status": "active"}},
            {"$group": {"_id": "$organization_id", "count": {"$sum": 1}}},
        ]):
            project_counts[row["_id"]] = row["count"]
        for row in teams_collection.aggregate([
            {"$match": {"organization_id": {"$in": org_ids}, "status": {"$ne": "deleted"}}},
            {"$group": {"_id": "$organization_id", "count": {"$sum": 1}}},
        ]):
            team_counts[row["_id"]] = row["count"]
    total = organizations_collection.count_documents(query)
    return ok("Organizations fetched", {"organizations": [org_summary(o, me, project_counts.get(o["_id"], 0), team_counts.get(o["_id"], 0)) for o in orgs], "total": total, "visible": len(orgs)})


@organization_bp.post("")
@jwt_required()
def create_org():
    me = current_user()
    if portal_role(me) not in ["Super User", "Admin"]:
        return warn("Warning: only a Super User or Admin can create organizations.")

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    visibility = data.get("visibility") or "Private"
    if not name:
        return fail("Organization name is required")
    if visibility not in ["Private", "Internal"]:
        visibility = "Private"

    now = datetime.now(timezone.utc)
    owner_role = "Admin" if portal_role(me) in ["Super User", "Admin"] else "Org Head"
    result = organizations_collection.insert_one({
        "name": name,
        "description": description,
        "visibility": visibility,
        "status": "active",
        "created_by": me["_id"],
        "members": [{"user_id": me["_id"], "role": owner_role, "status": "active", "joined_at": now}],
        "created_at": now,
        "updated_at": now,
    })
    sync_user_org_membership(result.inserted_id, me["_id"], owner_role, "active", me["_id"])
    activity_logs_collection.insert_one({"organization_id": result.inserted_id, "project_id": None, "user_id": me["_id"], "action": f'Organization "{name}" was created.', "type": "org_created", "created_at": now})
    return ok("Organization created", {"id": str(result.inserted_id)}, 201)


@organization_bp.get("/<org_id>")
@jwt_required()
def org_detail(org_id):
    me = current_user()
    org_obj_id = oid(org_id)
    if not org_obj_id:
        return fail("Invalid organization id")
    org = organizations_collection.find_one({"_id": org_obj_id, "status": {"$ne": "deleted"}})
    if not org:
        return fail("Organization not found", 404)
    if not is_super_user(me) and not org_role(org, me["_id"]):
        return warn("Warning: you do not have permission to access this organization.")
    try:
        members_limit = min(max(int(request.args.get("members_limit", 25) or 25), 1), 100)
    except Exception:
        members_limit = 25
    members_q = request.args.get("members_q") or ""
    return ok("Organization fetched", {"organization": org_detail_payload(org, me, members_limit, members_q)})


@organization_bp.patch("/<org_id>")
@jwt_required()
def update_org(org_id):
    me = current_user()
    org_obj_id = oid(org_id)
    if not org_obj_id:
        return fail("Invalid organization id")
    org = organizations_collection.find_one({"_id": org_obj_id, "status": {"$ne": "deleted"}})
    if not org:
        return fail("Organization not found", 404)
    if not can_manage_org(me, org):
        return warn("Warning: only Super User, Admin, or Org Head can edit organization config.")
    data = request.get_json() or {}
    update = {"updated_at": datetime.now(timezone.utc)}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return fail("Organization name is required")
        update["name"] = name
    if "description" in data:
        update["description"] = (data.get("description") or "").strip()
    if "visibility" in data and data.get("visibility") in ["Private", "Internal"]:
        update["visibility"] = data.get("visibility")
    organizations_collection.update_one({"_id": org_obj_id}, {"$set": update})
    return ok("Organization config updated")


@organization_bp.post("/<org_id>/members")
@jwt_required()
def add_member(org_id):
    me = current_user()
    org_obj_id = oid(org_id)
    if not org_obj_id:
        return fail("Invalid organization id")
    org = organizations_collection.find_one({"_id": org_obj_id, "status": {"$ne": "deleted"}})
    if not org:
        return fail("Organization not found", 404)
    if not can_manage_org(me, org):
        return warn("Warning: only Super User, Admin, or Org Head can add organization members.")
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    role = data.get("role") or "Member"
    if role not in ORG_ROLES:
        return fail("Invalid organization role")
    user = users_collection.find_one({"email": email, "is_active": True})
    if not user:
        return warn("Warning: portal user not found. A Super User must create this user before they can be added to an organization.")
    if any(m.get("user_id") == user["_id"] and m.get("status", "active") == "active" for m in org.get("members", [])):
        return warn("Warning: this user already belongs to this organization.")
    sync_user_org_membership(org_obj_id, user["_id"], role, "active", me["_id"])
    return ok("Organization member added")


@organization_bp.patch("/<org_id>/members/<user_id>")
@jwt_required()
def update_member(org_id, user_id):
    me = current_user()
    org_obj_id, target_id = oid(org_id), oid(user_id)
    if not org_obj_id or not target_id:
        return fail("Invalid id")
    org = organizations_collection.find_one({"_id": org_obj_id})
    if not org:
        return fail("Organization not found", 404)
    if not can_manage_org(me, org):
        return warn("Warning: you do not have permission to access this organization.")
    role = (request.get_json() or {}).get("role")
    if role not in ORG_ROLES:
        return fail("Invalid organization role")
    current_role = org_role(org, target_id)
    if current_role in ["Admin", "Org Head"] and role not in ["Admin", "Org Head"] and not active_org_managers(org, target_id):
        return warn("Warning: this organization must keep at least one Admin or Org Head. Promote another member before demoting this one.")
    sync_user_org_membership(org_obj_id, target_id, role, "active", me["_id"])
    return ok("Member role updated")


@organization_bp.delete("/<org_id>/members/<user_id>")
@jwt_required()
def remove_member(org_id, user_id):
    me = current_user()
    org_obj_id, target_id = oid(org_id), oid(user_id)
    if not org_obj_id or not target_id:
        return fail("Invalid id")
    org = organizations_collection.find_one({"_id": org_obj_id})
    if not org:
        return fail("Organization not found", 404)
    if not can_manage_org(me, org):
        return warn("Warning: you do not have permission to access this organization.")
    if target_id == org.get("created_by"):
        return warn("Warning: the organization creator cannot be removed. Transfer ownership or create a new org if needed.")
    if org_role(org, target_id) in ["Admin", "Org Head"] and not active_org_managers(org, target_id):
        return warn("Warning: this organization must keep at least one Admin or Org Head. Promote another member before removing this one.")
    linked_projects = active_projects_for_org_member(org_obj_id, target_id)
    if linked_projects:
        project_names = ", ".join([p.get("name", "Untitled Project") for p in linked_projects[:5]])
        more = "…" if len(linked_projects) > 5 else ""
        return warn(f"Warning: this member is still linked to active projects in this organization: {project_names}{more}. Remove or reassign them in those projects first.")
    mark_user_org_membership_removed(org_obj_id, target_id)
    return ok("Member removed")
