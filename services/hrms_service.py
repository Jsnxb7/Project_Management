from datetime import datetime, timezone
from bson import ObjectId

from database.db import (
    users_collection,
    employees_collection,
    attendance_collection,
    payroll_collection,
    performance_reviews_collection,
    leave_requests_collection,
    recruitment_candidates_collection,
    jobs_collection,
    applications_collection,
    resume_screening_collection,
)
from services.role_access import HRMS_ROLES, HR_POSITION_FAMILIES, normalize_role, role_permissions, user_role


def to_object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except Exception:
        return None


def current_employee_for_user(user_id):
    user_obj_id = to_object_id(user_id)
    if not user_obj_id:
        return None
    return employees_collection.find_one({"user_id": user_obj_id})


def serialize_dt(value):
    return value.isoformat() if value and hasattr(value, "isoformat") else value


def serialize_employee(employee):
    if not employee:
        return None
    manager = users_collection.find_one({"_id": employee.get("manager_id")}) if employee.get("manager_id") else None
    return {
        "id": str(employee["_id"]),
        "user_id": str(employee.get("user_id")) if employee.get("user_id") else None,
        "employee_code": employee.get("employee_code"),
        "name": employee.get("name"),
        "email": employee.get("email"),
        "phone": employee.get("phone"),
        "department": employee.get("department"),
        "designation": employee.get("designation"),
        "joining_date": serialize_dt(employee.get("joining_date")),
        "employment_status": employee.get("employment_status", "Active"),
        "manager_id": str(employee.get("manager_id")) if employee.get("manager_id") else None,
        "manager_name": manager.get("name") or manager.get("email") if manager else None,
        "manager_status": employee.get("manager_status", "missing" if not employee.get("manager_id") else "assigned"),
        "documents": employee.get("documents", []),
        "salary": employee.get("salary", {}),
        "work_history": employee.get("work_history", []),
    }


def manager_employee_ids(manager_user_id):
    manager_obj_id = to_object_id(manager_user_id)
    if not manager_obj_id:
        return []
    return [e["_id"] for e in employees_collection.find({"manager_id": manager_obj_id}, {"_id": 1})]


def scoped_employee_query(user):
    role = user_role(user)
    permissions = role_permissions(role)
    if permissions.get("can_view_company_dashboard") or permissions.get("can_manage_employees"):
        return {}

    own = current_employee_for_user(user["_id"])
    if not own:
        return {"_id": None}

    if role == "Senior Manager":
        ids = manager_employee_ids(user["_id"])
        ids.append(own["_id"])
        department = own.get("department")
        team_query = {"_id": {"$in": ids}}
        if department:
            return {"$or": [team_query, {"department": department}]}
        return team_query

    scoped_or = [{"_id": own["_id"]}]
    if own.get("department"):
        scoped_or.append({"department": own.get("department")})
    if own.get("manager_id"):
        scoped_or.append({"manager_id": own.get("manager_id")})
    return {"$or": scoped_or}


def attendance_summary(employee_query):
    today_key = datetime.now(timezone.utc).date().isoformat()
    employee_ids = [e["_id"] for e in employees_collection.find(employee_query, {"_id": 1})]
    if not employee_ids:
        return {"present": 0, "late": 0, "absent": 0, "overtime": 0, "leave": 0, "pending_reviews": 0, "total_logs": 0}
    base = {"employee_id": {"$in": employee_ids}}
    today = {**base, "date_key": today_key}
    return {
        "present": attendance_collection.count_documents({**today, "status": {"$in": ["present", "checked_in", "Present"]}}),
        "late": attendance_collection.count_documents({**today, "$or": [{"soft_tags": "late_checkin"}, {"late_mark": True}]}),
        "absent": attendance_collection.count_documents({**today, "status": {"$in": ["absent", "Absent"]}}),
        "overtime": attendance_collection.count_documents({**today, "soft_tags": "overtime"}),
        "leave": attendance_collection.count_documents({**today, "status": "leave"}),
        "pending_reviews": attendance_collection.count_documents({**base, "manager_status": {"$in": ["pending_review", "review_required"]}}),
        "total_logs": attendance_collection.count_documents(base),
    }


def dashboard_for(user):
    role = user_role(user)
    employee_query = scoped_employee_query(user)
    employee_ids = [e["_id"] for e in employees_collection.find(employee_query, {"_id": 1})]
    active_query = {**employee_query, "employment_status": "Active"}
    attendance = attendance_summary(employee_query)
    payroll_query = {"employee_id": {"$in": employee_ids}} if employee_ids else {"employee_id": None}

    common = {
        "role": role,
        "permissions": role_permissions(role),
        "employee_scope_count": len(employee_ids),
        "active_employees": employees_collection.count_documents(active_query),
        "attendance": attendance,
        "pending_reviews": performance_reviews_collection.count_documents({**payroll_query, "status": "Pending"}),
        "open_leave_requests": leave_requests_collection.count_documents({**payroll_query, "status": "Pending"}),
        "recent_activity": recent_hr_activity(employee_ids),
    }

    if role_permissions(role).get("can_view_company_dashboard"):
        common.update(company_dashboard())
    elif role_permissions(role).get("can_view_recruitment"):
        common.update(recruiter_dashboard())
    elif role == "Senior Manager":
        common.update(team_dashboard(user))
    else:
        common.update(employee_dashboard(user))
    return common


def company_dashboard():
    total = employees_collection.count_documents({})
    active = employees_collection.count_documents({"employment_status": "Active"})
    departments = list(employees_collection.aggregate([
        {"$group": {"_id": "$department", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    pipeline = list(applications_collection.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    return {
        "company": {
            "total_employees": total,
            "active_employees": active,
            "inactive_employees": max(total - active, 0),
            "departments": [{"name": row.get("_id") or "Unassigned", "count": row["count"]} for row in departments],
            "payroll_pending": payroll_collection.count_documents({"status": {"$in": ["Draft", "Pending Approval"]}}),
            "payroll_approved": payroll_collection.count_documents({"status": "Approved"}),
            "leave_pending": leave_requests_collection.count_documents({"status": {"$in": ["Pending", "pending"]}}),
            "manager_missing": employees_collection.count_documents({"employment_status": {"$ne": "Inactive"}, "$or": [{"manager_id": None}, {"manager_status": "missing"}]}),
            "attendance_reviews_pending": attendance_collection.count_documents({"manager_status": {"$in": ["pending_review", "review_required"]}}),
            "recruitment_pipeline": [{"status": row.get("_id") or "New", "count": row["count"]} for row in pipeline],
            "performance_reviews": performance_reviews_collection.count_documents({}),
        }
    }


def recruiter_dashboard():
    return {
        "recruitment": {
            "open_jobs": jobs_collection.count_documents({"status": "Open"}),
            "applications": applications_collection.count_documents({}),
            "shortlisted": applications_collection.count_documents({"status": "Shortlisted"}),
            "rejected": applications_collection.count_documents({"status": "Rejected"}),
            "ai_reports_ready": resume_screening_collection.count_documents({}),
        }
    }


def team_dashboard(user):
    team_ids = manager_employee_ids(user["_id"])
    return {
        "team": {
            "members": len(team_ids),
            "attendance_logs": attendance_collection.count_documents({"employee_id": {"$in": team_ids}}) if team_ids else 0,
            "leave_approvals": leave_requests_collection.count_documents({"employee_id": {"$in": team_ids}, "status": "Pending"}) if team_ids else 0,
            "reviews_pending": performance_reviews_collection.count_documents({"employee_id": {"$in": team_ids}, "status": "Pending"}) if team_ids else 0,
        }
    }


def employee_dashboard(user):
    employee = current_employee_for_user(user["_id"])
    employee_id = employee["_id"] if employee else None
    query = {"employee_id": employee_id} if employee_id else {"employee_id": None}
    return {
        "self": {
            "profile": serialize_employee(employee),
            "attendance_logs": attendance_collection.count_documents(query),
            "payslips": payroll_collection.count_documents(query),
            "reviews": performance_reviews_collection.count_documents(query),
            "leave_requests": leave_requests_collection.count_documents(query),
        }
    }


def recent_hr_activity(employee_ids):
    if not employee_ids:
        return []
    items = []
    for row in attendance_collection.find({"employee_id": {"$in": employee_ids}}).sort("created_at", -1).limit(5):
        items.append({
            "kind": "Attendance",
            "label": row.get("status", "Attendance log"),
            "created_at": serialize_dt(row.get("created_at") or row.get("date")),
        })
    for row in performance_reviews_collection.find({"employee_id": {"$in": employee_ids}}).sort("created_at", -1).limit(5):
        items.append({
            "kind": "Performance",
            "label": row.get("review_period", "Review"),
            "created_at": serialize_dt(row.get("created_at")),
        })
    return sorted(items, key=lambda item: item.get("created_at") or "", reverse=True)[:8]


def stamp(actor_id=None):
    now = datetime.now(timezone.utc)
    return {"created_at": now, "updated_at": now, "created_by": to_object_id(actor_id) if actor_id else None}
