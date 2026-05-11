from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, request
import re
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import teams_collection, organizations_collection, users_collection, projects_collection, tasks_collection
from utils.response import ok, fail, warn
from services.notification_service import create_notification
from services.activity_service import log_activity
from services.relation_service import (
    to_object_id,
    get_org_role,
    is_super_user_id,
    sync_user_org_membership,
    active_project_member,
)

team_bp = Blueprint("team_bp", __name__)
TEAM_ROLES = ["Team Lead", "Member"]


def now_utc():
    return datetime.now(timezone.utc)


def current_user_id():
    return ObjectId(get_jwt_identity())


def current_user():
    return users_collection.find_one({"_id": current_user_id()})


def portal_role(user):
    return user.get("portal_role", user.get("role", "Member")) if user else "Member"


def is_super_user(user):
    return portal_role(user) == "Super User"


def active_org_member(org, user_id):
    uid = to_object_id(user_id)
    return bool(org and uid and any(m.get("user_id") == uid and m.get("status", "active") == "active" for m in org.get("members", [])))


def can_manage_team(org_id, team=None, user_id=None):
    uid = to_object_id(user_id or current_user_id())
    if is_super_user_id(uid):
        return True
    if get_org_role(org_id, uid) in ["Admin", "Org Head"]:
        return True
    return bool(team and team.get("team_lead_id") == uid)


def can_assign_team_project(org_id, user_id=None):
    uid = to_object_id(user_id or current_user_id())
    return is_super_user_id(uid) or get_org_role(org_id, uid) in ["Admin", "Org Head"]


def user_map_for_ids(user_ids):
    ids = list({uid for uid in user_ids if uid})
    if not ids:
        return {}
    return {u["_id"]: u for u in users_collection.find({"_id": {"$in": ids}}, {"name": 1, "email": 1})}


def org_map_for_ids(org_ids):
    ids = list({oid for oid in org_ids if oid})
    if not ids:
        return {}
    return {o["_id"]: o for o in organizations_collection.find({"_id": {"$in": ids}}, {"name": 1})}


def project_map_for_ids(project_ids):
    ids = list({pid for pid in project_ids if pid})
    if not ids:
        return {}
    return {p["_id"]: p for p in projects_collection.find({"_id": {"$in": ids}, "status": "active"}, {"name": 1, "workflow_status": 1})}


def member_public(member, user_lookup=None):
    user_lookup = user_lookup or {}
    user = user_lookup.get(member.get("user_id"))
    if user is None and member.get("user_id"):
        user = users_collection.find_one({"_id": member.get("user_id")}, {"name": 1, "email": 1})
    return {
        "user_id": str(member.get("user_id")),
        "name": user.get("name") if user else "Unknown User",
        "email": user.get("email") if user else "",
        "role": member.get("role", "Member"),
        "status": member.get("status", "active"),
        "joined_at": member.get("joined_at").isoformat() if member.get("joined_at") else None,
    }


def team_public(team, include_members=True, org_lookup=None, lead_lookup=None, projects_lookup=None):
    org_lookup = org_lookup or {}
    lead_lookup = lead_lookup or {}
    projects_lookup = projects_lookup or {}
    org = org_lookup.get(team.get("organization_id"))
    if org is None and team.get("organization_id"):
        org = organizations_collection.find_one({"_id": team.get("organization_id")}, {"name": 1})
    lead = lead_lookup.get(team.get("team_lead_id"))
    if lead is None and team.get("team_lead_id"):
        lead = users_collection.find_one({"_id": team.get("team_lead_id")}, {"name": 1, "email": 1})
    project_ids = team.get("assigned_project_ids", [])
    projects = [projects_lookup[pid] for pid in project_ids if pid in projects_lookup]
    if projects_lookup == {} and project_ids:
        projects = list(projects_collection.find({"_id": {"$in": project_ids}, "status": "active"}, {"name": 1, "workflow_status": 1}))
    active_members = [m for m in team.get("members", []) if m.get("status", "active") == "active"]
    data = {
        "id": str(team["_id"]),
        "organization_id": str(team.get("organization_id")) if team.get("organization_id") else None,
        "organization_name": org.get("name") if org else "Unknown organization",
        "name": team.get("name"),
        "description": team.get("description", ""),
        "status": team.get("status", "active"),
        "team_lead_id": str(team.get("team_lead_id")) if team.get("team_lead_id") else None,
        "team_lead_name": lead.get("name") if lead else "No lead assigned",
        "member_count": len(active_members),
        "project_count": len(projects),
        "projects": [{"id": str(p["_id"]), "name": p.get("name"), "workflow_status": p.get("workflow_status", "Active")} for p in projects],
        "created_at": team.get("created_at").isoformat() if team.get("created_at") else None,
        "updated_at": team.get("updated_at").isoformat() if team.get("updated_at") else None,
    }
    if include_members:
        lookup = user_map_for_ids([m.get("user_id") for m in active_members])
        data["members"] = [member_public(m, lookup) for m in active_members]
    return data


def teams_public_bulk(teams, include_members=False):
    org_lookup = org_map_for_ids([t.get("organization_id") for t in teams])
    lead_lookup = user_map_for_ids([t.get("team_lead_id") for t in teams])
    project_ids = []
    for t in teams:
        project_ids.extend(t.get("assigned_project_ids", []))
    projects_lookup = project_map_for_ids(project_ids)
    return [team_public(t, include_members=include_members, org_lookup=org_lookup, lead_lookup=lead_lookup, projects_lookup=projects_lookup) for t in teams]


def ensure_project_member(project_id, user_id, role="Member", source_team_id=None, actor_id=None):
    pid, uid, tid = to_object_id(project_id), to_object_id(user_id), to_object_id(source_team_id)
    if not pid or not uid:
        return False
    project = projects_collection.find_one({"_id": pid, "status": "active"})
    if not project:
        return False
    existing = next((m for m in project.get("members", []) if m.get("user_id") == uid), None)
    now = now_utc()
    if existing:
        updates = {"members.$.status": "active", "members.$.updated_at": now, "updated_at": now}
        if existing.get("role") == "Member" and role == "Team Lead":
            updates["members.$.role"] = "Team Lead"
        projects_collection.update_one({"_id": pid, "members.user_id": uid}, {"$set": updates})
        if tid:
            projects_collection.update_one({"_id": pid, "members.user_id": uid}, {"$addToSet": {"members.$.source_team_ids": tid}})
    else:
        projects_collection.update_one({"_id": pid}, {"$push": {"members": {
            "user_id": uid,
            "role": role,
            "status": "active",
            "joined_at": now,
            "added_by": to_object_id(actor_id) if actor_id else None,
            "source_team_ids": [tid] if tid else [],
            "added_by_team_only": bool(tid),
        }}, "$set": {"updated_at": now}})
        create_notification(uid, f'You were added to project "{project.get("name", "Project")}" through your team.', "team_project_assigned", pid)
    return True


def remove_team_source_from_project(project_id, team_id):
    pid, tid = to_object_id(project_id), to_object_id(team_id)
    if not pid or not tid:
        return 0
    project = projects_collection.find_one({"_id": pid})
    if not project:
        return 0
    removed = 0
    for m in project.get("members", []):
        sources = [s for s in m.get("source_team_ids", []) if s != tid]
        if sources != m.get("source_team_ids", []):
            projects_collection.update_one({"_id": pid, "members.user_id": m.get("user_id")}, {"$set": {"members.$.source_team_ids": sources}})
            # If the user was only on the project through this team and has no tasks, mark removed.
            if not sources and m.get("added_by_team_only", False):
                tasks = tasks_collection.count_documents({"project_id": pid, "assigned_to": m.get("user_id"), "is_deleted": {"$ne": True}})
                if tasks == 0:
                    projects_collection.update_one({"_id": pid, "members.user_id": m.get("user_id")}, {"$set": {"members.$.status": "removed"}})
                    removed += 1
    projects_collection.update_one({"_id": pid}, {"$pull": {"team_assignments": {"team_id": tid}}, "$set": {"updated_at": now_utc()}})
    return removed


@team_bp.get("")
@jwt_required()
def list_teams():
    user_id = current_user_id()
    me = current_user()
    org_id = request.args.get("organization_id")
    q = (request.args.get("q") or "").strip()
    try:
        limit = min(max(int(request.args.get("limit", 100) or 100), 1), 200)
    except Exception:
        limit = 100
    query = {"status": {"$ne": "deleted"}}
    if org_id:
        oid = to_object_id(org_id)
        if not oid:
            return fail("Invalid organization id")
        query["organization_id"] = oid
    if q:
        query["$and"] = [{"$or": [
            {"name": {"$regex": re.escape(q), "$options": "i"}},
            {"description": {"$regex": re.escape(q), "$options": "i"}},
        ]}]
    if not is_super_user(me):
        org_ids = [m["_id"] for m in organizations_collection.find({"members": {"$elemMatch": {"user_id": user_id, "status": "active"}}, "status": {"$ne": "deleted"}}, {"_id": 1})]
        visibility_rule = {"$or": [{"organization_id": {"$in": org_ids}}, {"team_lead_id": user_id}, {"members": {"$elemMatch": {"user_id": user_id, "status": "active"}}}]}
        if "$and" in query:
            query["$and"].append(visibility_rule)
        else:
            query.update(visibility_rule)
    total = teams_collection.count_documents(query)
    teams = list(teams_collection.find(query).sort("updated_at", -1).limit(limit))
    return ok("Teams fetched", {"teams": teams_public_bulk(teams, include_members=False), "total": total, "visible": len(teams), "limit": limit})


@team_bp.post("")
@jwt_required()
def create_team():
    user_id = current_user_id()
    data = request.get_json() or {}
    org_id = to_object_id(data.get("organization_id"))
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    lead_email = (data.get("team_lead_email") or "").strip().lower()
    if not org_id:
        return fail("Organization is required")
    if not name:
        return fail("Team name is required")
    org = organizations_collection.find_one({"_id": org_id, "status": {"$ne": "deleted"}})
    if not org:
        return fail("Organization not found", 404)
    if not can_assign_team_project(org_id, user_id):
        return warn("Warning: only a Super User, Admin, or Org Head can create teams under an organization.")
    lead = users_collection.find_one({"email": lead_email, "is_active": True}) if lead_email else users_collection.find_one({"_id": user_id})
    if not lead:
        return warn("Warning: team lead must be an existing active portal user.")
    if not active_org_member(org, lead["_id"]):
        sync_user_org_membership(org_id, lead["_id"], "Team Lead", "active", user_id)
    else:
        if get_org_role(org_id, lead["_id"]) == "Member":
            sync_user_org_membership(org_id, lead["_id"], "Team Lead", "active", user_id)
    now = now_utc()
    result = teams_collection.insert_one({
        "organization_id": org_id,
        "name": name,
        "description": description,
        "team_lead_id": lead["_id"],
        "members": [{"user_id": lead["_id"], "role": "Team Lead", "status": "active", "joined_at": now, "added_by": user_id}],
        "assigned_project_ids": [],
        "status": "active",
        "created_by": user_id,
        "created_at": now,
        "updated_at": now,
    })
    return ok("Team created", {"id": str(result.inserted_id)}, 201)


@team_bp.get("/<team_id>")
@jwt_required()
def get_team(team_id):
    tid = to_object_id(team_id)
    if not tid:
        return fail("Invalid team id")
    team = teams_collection.find_one({"_id": tid, "status": {"$ne": "deleted"}})
    if not team:
        return fail("Team not found", 404)
    if not can_manage_team(team.get("organization_id"), team, current_user_id()) and not any(m.get("user_id") == current_user_id() and m.get("status") == "active" for m in team.get("members", [])):
        return warn("Warning: you do not have permission to view this team.")
    data = team_public(team)
    org = organizations_collection.find_one({"_id": team.get("organization_id")})
    org_member_ids = {m.get("user_id") for m in org.get("members", []) if m.get("status", "active") == "active"} if org else set()
    team_member_ids = {m.get("user_id") for m in team.get("members", []) if m.get("status", "active") == "active"}
    candidate_ids = list(org_member_ids - team_member_ids)
    candidate_lookup = user_map_for_ids(candidate_ids)
    candidates = []
    for uid in candidate_ids[:100]:
        u = candidate_lookup.get(uid)
        if u:
            candidates.append({"user_id": str(uid), "name": u.get("name"), "email": u.get("email"), "role": get_org_role(team.get("organization_id"), uid) or "Member"})
    data["org_candidates"] = candidates
    data["org_candidate_total"] = len(candidate_ids)
    data["can_manage"] = can_manage_team(team.get("organization_id"), team, current_user_id())
    data["can_assign_projects"] = can_assign_team_project(team.get("organization_id"), current_user_id())
    return ok("Team fetched", {"team": data})


@team_bp.post("/<team_id>/members")
@jwt_required()
def add_team_member(team_id):
    tid = to_object_id(team_id)
    user_id = current_user_id()
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not tid:
        return fail("Invalid team id")
    team = teams_collection.find_one({"_id": tid, "status": "active"})
    if not team:
        return fail("Team not found", 404)
    if not can_manage_team(team.get("organization_id"), team, user_id):
        return warn("Warning: only the Team Lead, Org Head/Admin, or Super User can add team members.")
    user = users_collection.find_one({"email": email, "is_active": True})
    if not user:
        return warn("Warning: user must exist in portal before joining a team.")
    org = organizations_collection.find_one({"_id": team.get("organization_id"), "status": {"$ne": "deleted"}})
    if not active_org_member(org, user["_id"]):
        sync_user_org_membership(team.get("organization_id"), user["_id"], "Member", "active", user_id)
    if any(m.get("user_id") == user["_id"] and m.get("status") == "active" for m in team.get("members", [])):
        return warn("Warning: this user is already in the team.")
    now = now_utc()
    teams_collection.update_one({"_id": tid}, {"$push": {"members": {"user_id": user["_id"], "role": "Member", "status": "active", "joined_at": now, "added_by": user_id}}, "$set": {"updated_at": now}})
    # Any project already assigned to the team should immediately include the new member.
    for pid in team.get("assigned_project_ids", []):
        ensure_project_member(pid, user["_id"], "Member", tid, user_id)
    return ok("Team member added and synced to assigned projects")


@team_bp.delete("/<team_id>/members/<member_id>")
@jwt_required()
def remove_team_member(team_id, member_id):
    tid, mid = to_object_id(team_id), to_object_id(member_id)
    user_id = current_user_id()
    if not tid or not mid:
        return fail("Invalid id")
    team = teams_collection.find_one({"_id": tid, "status": "active"})
    if not team:
        return fail("Team not found", 404)
    if not can_manage_team(team.get("organization_id"), team, user_id):
        return warn("Warning: only the Team Lead, Org Head/Admin, or Super User can remove team members.")
    if team.get("team_lead_id") == mid:
        return warn("Warning: assign a new team lead before removing the current team lead.")
    teams_collection.update_one({"_id": tid, "members.user_id": mid}, {"$set": {"members.$.status": "removed", "members.$.removed_at": now_utc(), "updated_at": now_utc()}})
    return ok("Team member removed. Existing project membership is kept to avoid deleting active work history.")


@team_bp.post("/<team_id>/projects")
@jwt_required()
def assign_project_to_team(team_id):
    tid = to_object_id(team_id)
    user_id = current_user_id()
    data = request.get_json() or {}
    project_id = to_object_id(data.get("project_id"))
    if not tid or not project_id:
        return fail("Team and project are required")
    team = teams_collection.find_one({"_id": tid, "status": "active"})
    project = projects_collection.find_one({"_id": project_id, "status": "active"})
    if not team or not project:
        return fail("Team or project not found", 404)
    if team.get("organization_id") != project.get("organization_id"):
        return warn("Warning: a team can only be assigned to projects inside the same organization.")
    if not can_assign_team_project(team.get("organization_id"), user_id):
        return warn("Warning: only Org Head/Admin or Super User can assign whole teams to projects.")
    now = now_utc()
    active_members = [m for m in team.get("members", []) if m.get("status", "active") == "active"]
    for member in active_members:
        ensure_project_member(project_id, member.get("user_id"), member.get("role", "Member"), tid, user_id)
    projects_collection.update_one({"_id": project_id}, {"$addToSet": {"team_assignments": {"team_id": tid, "assigned_at": now, "assigned_by": user_id}}, "$set": {"updated_at": now}})
    teams_collection.update_one({"_id": tid}, {"$addToSet": {"assigned_project_ids": project_id}, "$set": {"updated_at": now}})
    log_activity(project_id, user_id, "team_assigned", f'Team "{team.get("name")}" was assigned to this project.')
    return ok(f'Team assigned. {len(active_members)} team member(s) synced to the project.')


@team_bp.delete("/<team_id>/projects/<project_id>")
@jwt_required()
def unassign_project_from_team(team_id, project_id):
    tid, pid = to_object_id(team_id), to_object_id(project_id)
    user_id = current_user_id()
    if not tid or not pid:
        return fail("Invalid id")
    team = teams_collection.find_one({"_id": tid, "status": "active"})
    project = projects_collection.find_one({"_id": pid, "status": "active"})
    if not team or not project:
        return fail("Team or project not found", 404)
    if not can_assign_team_project(team.get("organization_id"), user_id):
        return warn("Warning: only Org Head/Admin or Super User can unassign whole teams from projects.")
    teams_collection.update_one({"_id": tid}, {"$pull": {"assigned_project_ids": pid}, "$set": {"updated_at": now_utc()}})
    remove_team_source_from_project(pid, tid)
    log_activity(pid, user_id, "team_unassigned", f'Team "{team.get("name")}" was unassigned from this project.')
    return ok("Team unassigned. Explicit project members and users with tasks are kept for work history.")


@team_bp.delete("/<team_id>")
@jwt_required()
def archive_team(team_id):
    tid = to_object_id(team_id)
    user_id = current_user_id()
    if not tid:
        return fail("Invalid team id")
    team = teams_collection.find_one({"_id": tid, "status": "active"})
    if not team:
        return fail("Team not found", 404)
    if not can_assign_team_project(team.get("organization_id"), user_id):
        return warn("Warning: only Org Head/Admin or Super User can archive teams.")
    teams_collection.update_one({"_id": tid}, {"$set": {"status": "archived", "updated_at": now_utc()}})
    return ok("Team archived")
