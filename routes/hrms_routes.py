from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import (
    users_collection,
    employees_collection,
    attendance_collection,
    payroll_collection,
    performance_reviews_collection,
)
from utils.response import ok, fail, warn
from services.hrms_service import (
    HR_POSITION_FAMILIES,
    HRMS_ROLES,
    dashboard_for,
    normalize_role,
    role_permissions,
    scoped_employee_query,
    serialize_employee,
    stamp,
    to_object_id,
    user_role,
)


hrms_bp = Blueprint("hrms_bp", __name__)


def current_user():
    user_id = to_object_id(get_jwt_identity())
    return users_collection.find_one({"_id": user_id}) if user_id else None


def require_permission(permission):
    user = current_user()
    if not user:
        return None, fail("User not found", 404)
    if not role_permissions(user_role(user)).get(permission):
        return user, warn("Warning: your HRMS role cannot perform this action.")
    return user, None


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0


@hrms_bp.get("/roles")
@jwt_required()
def roles():
    return ok("HRMS roles fetched", {
        "roles": HRMS_ROLES,
        "position_families": HR_POSITION_FAMILIES,
        "permissions": {role: role_permissions(role) for role in HRMS_ROLES},
    })


@hrms_bp.get("/dashboard")
@jwt_required()
def hrms_dashboard():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("HRMS dashboard fetched", dashboard_for(user))


@hrms_bp.get("/employees")
@jwt_required()
def list_employees():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    q = (request.args.get("q") or "").strip()
    query = scoped_employee_query(user)
    if q:
        regex = {"$regex": q, "$options": "i"}
        query = {"$and": [query, {"$or": [{"name": regex}, {"email": regex}, {"department": regex}, {"designation": regex}, {"employee_code": regex}]}]}
    employees = list(employees_collection.find(query).sort("name", 1).limit(100))
    return ok("Employees fetched", {"employees": [serialize_employee(e) for e in employees]})


@hrms_bp.post("/employees")
@jwt_required()
def create_employee():
    user, error = require_permission("can_manage_employees")
    if error:
        return error
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not name:
        return fail("Employee name is required")
    if not email:
        return fail("Employee email is required")

    manager_id = to_object_id(data.get("manager_id"))
    user_id = to_object_id(data.get("user_id"))
    employee = {
        "user_id": user_id,
        "employee_code": (data.get("employee_code") or "").strip(),
        "name": name,
        "email": email,
        "phone": (data.get("phone") or "").strip(),
        "department": (data.get("department") or "Unassigned").strip(),
        "designation": (data.get("designation") or "Employee").strip(),
        "joining_date": parse_date(data.get("joining_date")) or datetime.now(timezone.utc),
        "employment_status": data.get("employment_status") or "Active",
        "manager_id": manager_id,
        "documents": data.get("documents") or [],
        "salary": data.get("salary") or {},
        "work_history": data.get("work_history") or [],
        **stamp(user["_id"]),
    }
    result = employees_collection.insert_one(employee)
    if user_id:
        users_collection.update_one({"_id": user_id}, {"$set": {"hrms_role": normalize_role(data.get("hrms_role") or "Employee"), "role": normalize_role(data.get("hrms_role") or "Employee"), "updated_at": datetime.now(timezone.utc)}})
    return ok("Employee created", {"id": str(result.inserted_id)}, 201)


@hrms_bp.patch("/employees/<employee_id>")
@jwt_required()
def update_employee(employee_id):
    user, error = require_permission("can_manage_employees")
    if error:
        return error
    obj_id = to_object_id(employee_id)
    if not obj_id:
        return fail("Invalid employee id")
    data = request.get_json() or {}
    allowed = ["employee_code", "name", "email", "phone", "department", "designation", "employment_status", "documents", "salary", "work_history"]
    updates = {key: data[key] for key in allowed if key in data}
    if "manager_id" in data:
        updates["manager_id"] = to_object_id(data.get("manager_id"))
    if "joining_date" in data:
        updates["joining_date"] = parse_date(data.get("joining_date"))
    updates["updated_at"] = datetime.now(timezone.utc)
    result = employees_collection.update_one({"_id": obj_id}, {"$set": updates})
    if result.matched_count == 0:
        return fail("Employee not found", 404)
    return ok("Employee updated")


@hrms_bp.post("/attendance")
@jwt_required()
def record_attendance():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    data = request.get_json() or {}
    employee_id = to_object_id(data.get("employee_id"))
    if not employee_id:
        employee = employees_collection.find_one({"user_id": user["_id"]})
        employee_id = employee["_id"] if employee else None
    if not employee_id:
        return fail("Employee profile is required before attendance can be recorded")
    employee = employees_collection.find_one({"_id": employee_id})
    if not employee:
        return fail("Employee not found", 404)
    permissions = role_permissions(user_role(user))
    if employee.get("user_id") != user["_id"] and not (permissions["can_manage_employees"] or permissions["can_view_team_dashboard"]):
        return warn("Warning: your HRMS role cannot record attendance for this employee.")

    check_in = parse_date(data.get("check_in"))
    check_out = parse_date(data.get("check_out"))
    working_hours = money(data.get("working_hours"))
    if check_in and check_out:
        working_hours = round(max((check_out - check_in).total_seconds(), 0) / 3600, 2)
    item = {
        "employee_id": employee_id,
        "department": employee.get("department"),
        "date": parse_date(data.get("date")) or datetime.now(timezone.utc),
        "check_in": check_in,
        "check_out": check_out,
        "working_hours": working_hours,
        "late_mark": bool(data.get("late_mark")),
        "status": data.get("status") or "Present",
        **stamp(user["_id"]),
    }
    result = attendance_collection.insert_one(item)
    return ok("Attendance recorded", {"id": str(result.inserted_id)}, 201)


@hrms_bp.get("/attendance")
@jwt_required()
def list_attendance():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    employee_ids = [e["_id"] for e in employees_collection.find(scoped_employee_query(user), {"_id": 1})]
    rows = list(attendance_collection.find({"employee_id": {"$in": employee_ids}}).sort("date", -1).limit(100))
    return ok("Attendance logs fetched", {"logs": [{
        "id": str(row["_id"]),
        "employee_id": str(row.get("employee_id")),
        "date": row.get("date").isoformat() if row.get("date") else None,
        "status": row.get("status"),
        "working_hours": row.get("working_hours", 0),
        "late_mark": row.get("late_mark", False),
    } for row in rows]})


@hrms_bp.post("/payroll")
@jwt_required()
def create_payroll():
    user, error = require_permission("can_manage_payroll")
    if error:
        return error
    data = request.get_json() or {}
    employee_id = to_object_id(data.get("employee_id"))
    employee = employees_collection.find_one({"_id": employee_id}) if employee_id else None
    if not employee:
        return fail("Employee is required")
    basic = money(data.get("basic_salary") or employee.get("salary", {}).get("basic"))
    allowances = money(data.get("allowances") or employee.get("salary", {}).get("allowances"))
    deductions = money(data.get("deductions"))
    tax = money(data.get("tax"))
    net_salary = round(basic + allowances - deductions - tax, 2)
    result = payroll_collection.insert_one({
        "employee_id": employee_id,
        "period": data.get("period") or datetime.now(timezone.utc).strftime("%Y-%m"),
        "basic_salary": basic,
        "allowances": allowances,
        "deductions": deductions,
        "tax": tax,
        "net_salary": net_salary,
        "attendance_based": bool(data.get("attendance_based", True)),
        "status": data.get("status") or "Draft",
        "payslip_url": data.get("payslip_url"),
        **stamp(user["_id"]),
    })
    return ok("Payroll entry created", {"id": str(result.inserted_id), "net_salary": net_salary}, 201)


@hrms_bp.post("/performance")
@jwt_required()
def create_performance_review():
    user, error = require_permission("can_review_performance")
    if error:
        return error
    data = request.get_json() or {}
    employee_id = to_object_id(data.get("employee_id"))
    if not employee_id or not employees_collection.find_one({"_id": employee_id}):
        return fail("Employee is required")
    result = performance_reviews_collection.insert_one({
        "employee_id": employee_id,
        "manager_id": user["_id"],
        "review_period": data.get("review_period") or datetime.now(timezone.utc).strftime("%Y"),
        "manager_rating": money(data.get("manager_rating")),
        "kpis": data.get("kpis") or [],
        "goals": data.get("goals") or [],
        "feedback": data.get("feedback") or "",
        "promotion_recommendation": bool(data.get("promotion_recommendation")),
        "status": data.get("status") or "Pending",
        **stamp(user["_id"]),
    })
    return ok("Performance review created", {"id": str(result.inserted_id)}, 201)
