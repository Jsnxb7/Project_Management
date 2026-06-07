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
    leave_requests_collection,
    hrms_messages_collection,
)
from utils.response import ok, fail, warn
import services.attendance_service as att
import services.payroll_performance_service as pps
from services.ui_service import ui_shell_for_role
from services.dashboard_service import dashboard_summary_for
from services.hrms_service import (
    HR_POSITION_FAMILIES,
    HRMS_ROLES,
    normalize_role,
    role_permissions,
    assigned_employee_query,
    department_employee_query,
    primary_super_user_id,
    scoped_employee_query,
    serialize_employee,
    stamp,
    to_object_id,
    user_role,
)


hrms_bp = Blueprint("hrms_bp", __name__)


def current_user():
    user_id = to_object_id(get_jwt_identity())
    return users_collection.find_one({"_id": user_id, "is_active": True}) if user_id else None


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


def serialize_payroll(row):
    return {
        "id": str(row["_id"]),
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "period": row.get("period"),
        "basic_salary": row.get("basic_salary", 0),
        "allowances": row.get("allowances", 0),
        "deductions": row.get("deductions", 0),
        "tax": row.get("tax", 0),
        "net_salary": row.get("net_salary", 0),
        "status": row.get("status", "Draft"),
        "payslip_url": row.get("payslip_url"),
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
    }


def serialize_review(row):
    return {
        "id": str(row["_id"]),
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "manager_id": str(row.get("manager_id")) if row.get("manager_id") else None,
        "review_period": row.get("review_period"),
        "manager_rating": row.get("manager_rating", 0),
        "kpis": row.get("kpis", []),
        "goals": row.get("goals", []),
        "feedback": row.get("feedback", ""),
        "promotion_recommendation": row.get("promotion_recommendation", False),
        "status": row.get("status", "Pending"),
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
    }


def scoped_employee_ids(user):
    return [e["_id"] for e in employees_collection.find(scoped_employee_query(user), {"_id": 1})]


def can_access_employee(user, employee_id):
    if not employee_id:
        return False
    return employees_collection.count_documents({"$and": [scoped_employee_query(user), {"_id": employee_id}]}) > 0


def conversation_key_for(user_id_a, user_id_b):
    return ":".join(sorted([str(user_id_a), str(user_id_b)]))


def has_message_conversation(user_id_a, user_id_b):
    if not user_id_a or not user_id_b:
        return False
    key = conversation_key_for(user_id_a, user_id_b)
    return hrms_messages_collection.count_documents({
        "conversation_key": key,
        "participant_user_ids": {"$all": [user_id_a, user_id_b]},
    }, limit=1) > 0


def can_open_message_thread(user, target_employee):
    if not target_employee or not target_employee.get("user_id"):
        return False
    return can_access_employee(user, target_employee["_id"]) or has_message_conversation(user["_id"], target_employee["user_id"])


def message_employee_summary(employee):
    if not employee:
        return None
    return {
        "id": str(employee["_id"]),
        "user_id": str(employee.get("user_id")) if employee.get("user_id") else None,
        "name": employee.get("name"),
        "email": employee.get("email"),
        "department": employee.get("department"),
        "designation": employee.get("designation"),
    }


def serialize_message(row, me_user_id=None):
    return {
        "id": str(row["_id"]),
        "conversation_key": row.get("conversation_key"),
        "sender_user_id": str(row.get("sender_user_id")) if row.get("sender_user_id") else None,
        "receiver_user_id": str(row.get("receiver_user_id")) if row.get("receiver_user_id") else None,
        "sender_employee_id": str(row.get("sender_employee_id")) if row.get("sender_employee_id") else None,
        "receiver_employee_id": str(row.get("receiver_employee_id")) if row.get("receiver_employee_id") else None,
        "body": row.get("body", ""),
        "is_mine": str(row.get("sender_user_id")) == str(me_user_id) if me_user_id else False,
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
    }




@hrms_bp.get("/ui-shell")
@jwt_required()
def ui_shell():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("UI shell fetched", ui_shell_for_role(user_role(user)))

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
    return ok("HRMS dashboard fetched", dashboard_summary_for(user))


@hrms_bp.get("/dashboard/summary")
@jwt_required()
def hrms_dashboard_summary():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("HRMS dashboard summary fetched", dashboard_summary_for(user))


@hrms_bp.get("/employees")
@jwt_required()
def list_employees():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    q = (request.args.get("q") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = max(1, min(int(request.args.get("limit", 25)), 100))
    except (TypeError, ValueError):
        limit = 25
    skip = (page - 1) * limit
    search_query = {}
    if q:
        regex = {"$regex": q, "$options": "i"}
        search_query = {"$or": [{"name": regex}, {"email": regex}, {"department": regex}, {"designation": regex}, {"employee_code": regex}]}

    def with_search(base_query):
        return {"$and": [base_query, search_query]} if search_query else base_query

    permissions = role_permissions(user_role(user))
    all_query = with_search({} if permissions.get("is_super_user") else department_employee_query(user))
    assigned_query = with_search(assigned_employee_query(user))
    total = employees_collection.count_documents(all_query)
    pages = max(1, (total + limit - 1) // limit)
    employees = list(employees_collection.find(all_query).sort("name", 1).skip(skip).limit(limit))
    assigned_employees = list(employees_collection.find(assigned_query).sort("name", 1).limit(50))
    return ok("Employees fetched", {
        "employees": [serialize_employee(e) for e in employees],
        "department_employees": [serialize_employee(e) for e in employees],
        "assigned_employees": [serialize_employee(e) for e in assigned_employees],
        "meta": {"page": page, "limit": limit, "total": total, "pages": pages, "has_next": page < pages, "has_prev": page > 1},
    })


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

    raw_manager_ids = data.get("manager_ids") or data.get("manager_user_ids") or []
    if not raw_manager_ids and data.get("manager_id"):
        raw_manager_ids = [data.get("manager_id")]
    manager_ids = []
    for value in raw_manager_ids:
        manager_id = to_object_id(value)
        if manager_id and manager_id not in manager_ids:
            manager_ids.append(manager_id)
    if not manager_ids:
        default_manager_id = primary_super_user_id(exclude_user_id=to_object_id(data.get("user_id")))
        if default_manager_id:
            manager_ids.append(default_manager_id)
    manager_id = manager_ids[0] if manager_ids else None
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
        "manager_ids": manager_ids,
        "manager_status": "assigned" if manager_ids else "missing",
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
    if "manager_id" in data or "manager_ids" in data or "manager_user_ids" in data:
        raw_manager_ids = data.get("manager_ids") or data.get("manager_user_ids") or []
        if not raw_manager_ids and data.get("manager_id"):
            raw_manager_ids = [data.get("manager_id")]
        manager_ids = []
        for value in raw_manager_ids:
            manager_id = to_object_id(value)
            if manager_id and manager_id not in manager_ids:
                manager_ids.append(manager_id)
        updates["manager_id"] = manager_ids[0] if manager_ids else None
        updates["manager_ids"] = manager_ids
        updates["manager_status"] = "assigned" if manager_ids else "missing"
    if "joining_date" in data:
        updates["joining_date"] = parse_date(data.get("joining_date"))
    updates["updated_at"] = datetime.now(timezone.utc)
    result = employees_collection.update_one({"_id": obj_id}, {"$set": updates})
    if result.matched_count == 0:
        return fail("Employee not found", 404)
    return ok("Employee updated")



@hrms_bp.get("/attendance")
@jwt_required()
def list_attendance():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    employee_id = request.args.get("employee_id")
    start = request.args.get("start")
    end = request.args.get("end")
    logs = att.list_attendance(user, employee_id=employee_id, start=start, end=end)
    return ok("Attendance logs fetched", {"logs": logs})


@hrms_bp.get("/attendance/calendar")
@jwt_required()
def attendance_calendar():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Attendance calendar fetched", att.calendar_payload(user, request.args.get("employee_id"), request.args.get("month")))


@hrms_bp.get("/attendance/my")
@jwt_required()
def my_attendance():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    employee = employees_collection.find_one({"user_id": user["_id"]})
    employee_id = str(employee["_id"]) if employee else None
    return ok("My attendance fetched", {
        "employee": serialize_employee(employee),
        "calendar": att.calendar_payload(user, employee_id, request.args.get("month")),
    })


@hrms_bp.get("/attendance/team")
@jwt_required()
def team_attendance():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    employees = [serialize_employee(e) for e in employees_collection.find(att.team_employee_query(user)).sort("name", 1).limit(200)]
    return ok("Team attendance fetched", {
        "employees": employees,
        "logs": att.list_attendance(user, start=request.args.get("start"), end=request.args.get("end")),
        "pending_reviews": att.pending_reviews(user),
        "pending_leaves": att.pending_leave_for_manager(user),
    })


@hrms_bp.get("/attendance/user/<employee_id>")
@jwt_required()
def user_attendance(employee_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Employee attendance fetched", att.calendar_payload(user, employee_id, request.args.get("month")))


@hrms_bp.post("/attendance/check-in")
@jwt_required()
def attendance_check_in():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    try:
        row, error = att.check_in(user, request.get_json() or {})
    except Exception as exc:
        return fail(f"Check-in failed: {exc}", 500)
    if error and row:
        return warn(error, {"record": row})
    if error:
        return fail(error)
    return ok("Check-in recorded", {"record": row}, 201)


@hrms_bp.post("/attendance/check-out")
@jwt_required()
def attendance_check_out():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    try:
        row, error = att.check_out(user, request.get_json() or {})
    except Exception as exc:
        return fail(f"Checkout failed: {exc}", 500)
    if error and row:
        return warn(error, {"record": row})
    if error:
        return fail(error)
    return ok("Checkout recorded", {"record": row})


@hrms_bp.post("/attendance")
@jwt_required()
def record_attendance():
    """Compatibility endpoint: check-in/check-out/manual record through the new attendance service."""
    user = current_user()
    if not user:
        return fail("User not found", 404)
    data = request.get_json() or {}
    if data.get("check_out"):
        row, error = att.check_out(user, data)
    else:
        row, error = att.check_in(user, data)
    if error and row:
        return warn(error, {"record": row})
    if error:
        return fail(error)
    return ok("Attendance recorded", {"record": row}, 201)


@hrms_bp.get("/attendance/reviews/pending")
@jwt_required()
def pending_attendance_reviews():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Pending attendance reviews fetched", {"reviews": att.pending_reviews(user)})


@hrms_bp.post("/attendance/<attendance_id>/confirm")
@jwt_required()
def confirm_attendance(attendance_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    data = request.get_json() or {}
    row, error = att.review_attendance(user, attendance_id, data.get("action") or "confirm_present", data.get("note") or "", data.get("tags"), data.get("overrides"))
    if error:
        return warn(error)
    return ok("Attendance confirmed", {"record": row})


@hrms_bp.post("/attendance/<attendance_id>/excuse")
@jwt_required()
def excuse_attendance(attendance_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    data = request.get_json() or {}
    row, error = att.review_attendance(user, attendance_id, data.get("action") or "excuse_late", data.get("note") or "")
    if error:
        return warn(error)
    return ok("Attendance excused", {"record": row})


@hrms_bp.post("/attendance/<attendance_id>/override")
@jwt_required()
def override_attendance(attendance_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    data = request.get_json() or {}
    row, error = att.review_attendance(user, attendance_id, data.get("action") or "confirm_present", data.get("note") or "Manual override", data.get("tags"), data.get("overrides") or data)
    if error:
        return warn(error)
    return ok("Attendance overridden", {"record": row})


@hrms_bp.get("/attendance/rules")
@jwt_required()
def attendance_rules():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Attendance rules fetched", {"rules": att.get_rules()})


@hrms_bp.post("/attendance/rules")
@jwt_required()
def update_attendance_rules():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    if not role_permissions(user_role(user)).get("can_manage_attendance_rules"):
        return warn("Only Super User can update attendance rules.")
    return ok("Attendance rules updated", {"rules": att.save_rules(request.get_json() or {}, user["_id"])})


@hrms_bp.post("/leave/request")
@jwt_required()
def request_leave():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = att.request_leave(user, request.get_json() or {})
    if error:
        return fail(error)
    return ok("Leave request submitted", {"leave": row}, 201)


@hrms_bp.get("/leave/my")
@jwt_required()
def my_leave_requests():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    employee = employees_collection.find_one({"user_id": user["_id"]})
    if not employee:
        return ok("My leave requests fetched", {"leaves": []})
    rows = leave_requests_collection.find({"employee_id": employee["_id"]}).sort("created_at", -1).limit(100)
    return ok("My leave requests fetched", {"leaves": [att.serialize_leave(r) for r in rows]})


@hrms_bp.get("/leave/team")
@jwt_required()
def team_leave_requests():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Team leave requests fetched", {"leaves": att.pending_leave_for_manager(user)})


@hrms_bp.post("/leave/<leave_id>/approve")
@jwt_required()
def approve_leave(leave_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = att.review_leave(user, leave_id, "approve", (request.get_json() or {}).get("note") or "")
    if error:
        return warn(error)
    return ok("Leave approved", {"leave": row})


@hrms_bp.post("/leave/<leave_id>/reject")
@jwt_required()
def reject_leave(leave_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = att.review_leave(user, leave_id, "reject", (request.get_json() or {}).get("note") or "")
    if error:
        return warn(error)
    return ok("Leave rejected", {"leave": row})


@hrms_bp.get("/managers")
@jwt_required()
def list_manager_options():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Managers fetched", {"managers": att.manager_options(user)})


@hrms_bp.get("/managers/team")
@jwt_required()
def manager_team():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    employees = [serialize_employee(e) for e in employees_collection.find(att.team_employee_query(user)).sort("name", 1).limit(200)]
    return ok("Manager team fetched", {"employees": employees})


@hrms_bp.post("/users/<user_id>/assign-manager")
@jwt_required()
def assign_manager(user_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    data = request.get_json() or {}
    row, error = att.assign_manager(user, user_id, data.get("manager_user_id") or data.get("manager_id"), data.get("manager_user_ids") or data.get("manager_ids"))
    if error:
        return warn(error)
    return ok("Manager assigned", {"employee": row})


@hrms_bp.post("/managers/repair")
@jwt_required()
def repair_manager_assignments():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    if not role_permissions(user_role(user)).get("is_super_user"):
        return warn("Only Super User can repair manager assignments.")
    count = att.ensure_manager_assignments(user["_id"])
    return ok("Manager assignments checked", {"updated": count})


@hrms_bp.post("/attendance/meeting")
@jwt_required()
def create_attendance_meeting():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = att.create_meeting(user, request.get_json() or {})
    if error:
        return warn(error)
    return ok("Meeting scheduled", {"meeting": row}, 201)


@hrms_bp.get("/attendance/meetings/my")
@jwt_required()
def my_attendance_meetings():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Attendance meetings fetched", {"meetings": att.list_meetings(user)})


@hrms_bp.get("/attendance/meetings/team")
@jwt_required()
def team_attendance_meetings():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Attendance meetings fetched", {"meetings": att.list_meetings(user)})


@hrms_bp.post("/attendance/meeting/<meeting_id>/complete")
@jwt_required()
def complete_attendance_meeting(meeting_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = att.update_meeting(user, meeting_id, "completed")
    if error:
        return warn(error)
    return ok("Meeting completed", {"meeting": row})


@hrms_bp.post("/attendance/meeting/<meeting_id>/cancel")
@jwt_required()
def cancel_attendance_meeting(meeting_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = att.update_meeting(user, meeting_id, "cancelled")
    if error:
        return warn(error)
    return ok("Meeting cancelled", {"meeting": row})


@hrms_bp.post("/attendance/correction")
@jwt_required()
def attendance_correction():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = att.request_correction(user, request.get_json() or {})
    if error:
        return fail(error)
    return ok("Attendance correction requested", {"correction": row}, 201)


@hrms_bp.get("/attendance/corrections")
@jwt_required()
def attendance_corrections():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    return ok("Attendance corrections fetched", {"corrections": att.list_corrections(user)})




@hrms_bp.get("/payroll")
@jwt_required()
def payroll_workspace():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    if not role_permissions(user_role(user)).get("can_view_payroll"):
        return warn("Warning: your HRMS role cannot view payroll.")
    return ok("Payroll workspace fetched", pps.payroll_workspace(user))


@hrms_bp.post("/payroll")
@jwt_required()
def create_simple_payroll():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.generate_payroll(user, request.get_json() or {})
    if error:
        return warn(error)
    return ok("Payroll generated", row, 201)


@hrms_bp.post("/payroll/profile")
@jwt_required()
def upsert_payroll_profile():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.upsert_profile(user, request.get_json() or {})
    if error:
        return warn(error)
    return ok("Payroll profile saved", {"profile": row})


@hrms_bp.post("/payroll/profiles/generate")
@jwt_required()
def generate_payroll_profiles():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.bulk_generate_profiles(user, request.get_json() or {})
    if error:
        return warn(error)
    return ok("Salary profiles generated", row, 201)


@hrms_bp.post("/payroll/generate")
@jwt_required()
def generate_payroll_batch():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.generate_payroll(user, request.get_json() or {})
    if error:
        return warn(error)
    return ok("Payroll generated", row, 201)


@hrms_bp.post("/payroll/adjustments/<adjustment_id>/toggle")
@jwt_required()
def toggle_payroll_adjustment(adjustment_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.toggle_adjustment(user, adjustment_id, bool((request.get_json() or {}).get("included", True)))
    if error:
        return warn(error)
    return ok("Payroll adjustment updated", {"adjustment": row})


@hrms_bp.post("/payroll/items/<item_id>/confirm")
@jwt_required()
def confirm_simple_payroll(item_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.confirm_payroll(user, item_id, (request.get_json() or {}).get("action") or "confirm")
    if error:
        return warn(error)
    return ok("Payroll confirmation updated", {"item": row})


@hrms_bp.patch("/payroll/items/<item_id>")
@jwt_required()
def edit_simple_payroll(item_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.edit_payroll_item(user, item_id, request.get_json() or {})
    if error:
        return warn(error)
    return ok("Payroll item updated", {"item": row})


@hrms_bp.post("/payroll/items/<item_id>/pay")
@jwt_required()
def pay_simple_payroll(item_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.payout_payroll(user, item_id)
    if error:
        return warn(error)
    return ok("Payroll marked as paid", {"item": row})


@hrms_bp.post("/payroll/custom-pay")
@jwt_required()
def custom_payroll_now():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.custom_payroll_payout(user, request.get_json() or {})
    if error:
        return warn(error)
    return ok("Custom payroll paid", {"item": row}, 201)


@hrms_bp.get("/performance")
@jwt_required()
def performance_workspace():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    if not role_permissions(user_role(user)).get("can_view_performance"):
        return warn("Warning: your HRMS role cannot view performance.")
    return ok("Performance workspace fetched", pps.performance_workspace(user))


@hrms_bp.post("/performance")
@jwt_required()
def assign_simple_performance_goal():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.assign_goals(user, request.get_json() or {})
    if error:
        return warn(error, row)
    return ok("Performance goals assigned", row, 201)


@hrms_bp.post("/performance/templates")
@jwt_required()
def create_performance_template():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.create_template(user, request.get_json() or {})
    if error:
        return warn(error)
    return ok("Performance template created", {"template": row}, 201)


@hrms_bp.post("/performance/goals")
@jwt_required()
def assign_performance_goals():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.assign_goals(user, request.get_json() or {})
    if error:
        return warn(error, row)
    return ok("Performance goals assigned", row, 201)


@hrms_bp.post("/performance/goals/<goal_id>/checklist/<item_id>/check")
@jwt_required()
def check_performance_item(goal_id, item_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.update_checklist(user, goal_id, item_id, request.get_json() or {}, "employee_check")
    if error:
        return warn(error)
    return ok("Checklist updated", {"goal": row})


@hrms_bp.post("/performance/goals/<goal_id>/checklist/<item_id>/verify")
@jwt_required()
def verify_performance_item(goal_id, item_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    row, error = pps.update_checklist(user, goal_id, item_id, request.get_json() or {}, "manager_verify")
    if error:
        return warn(error)
    return ok("Checklist verification updated", {"goal": row})


@hrms_bp.get("/messages/conversations")
@jwt_required()
def list_message_conversations():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    if not role_permissions(user_role(user)).get("can_message_employees"):
        return warn("Warning: your HRMS role cannot use employee messages.")

    rows = list(hrms_messages_collection.find({"participant_user_ids": user["_id"]}).sort("updated_at", -1).limit(100))
    conversations = {}
    for row in rows:
        key = row.get("conversation_key")
        if key in conversations:
            continue
        participant_ids = [pid for pid in row.get("participant_user_ids", []) if pid != user["_id"]]
        other_user_id = participant_ids[0] if participant_ids else row.get("receiver_user_id")
        other_employee = employees_collection.find_one({"user_id": other_user_id}) if other_user_id else None
        conversations[key] = {
            "conversation_key": key,
            "employee": message_employee_summary(other_employee),
            "last_message": serialize_message(row, user["_id"]),
            "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
        }
    return ok("Conversations fetched", {"conversations": list(conversations.values())})


@hrms_bp.get("/messages/<employee_id>")
@jwt_required()
def list_messages(employee_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    if not role_permissions(user_role(user)).get("can_message_employees"):
        return warn("Warning: your HRMS role cannot use employee messages.")

    target_id = to_object_id(employee_id)
    if not target_id:
        return fail("Invalid employee id")
    target = employees_collection.find_one({"_id": target_id})
    own = employees_collection.find_one({"user_id": user["_id"]})
    if not target or not target.get("user_id"):
        return fail("Employee is not available for messaging", 404)
    if own and target["_id"] == own["_id"]:
        return fail("You cannot open a message thread with yourself")
    if not can_open_message_thread(user, target):
        return warn("Warning: you can only message employees in your allowed department or team scope.")

    key = conversation_key_for(user["_id"], target["user_id"])
    rows = list(hrms_messages_collection.find({"conversation_key": key}).sort("created_at", 1).limit(200))
    return ok("Messages fetched", {"employee": message_employee_summary(target), "messages": [serialize_message(row, user["_id"]) for row in rows]})


@hrms_bp.post("/messages/<employee_id>")
@jwt_required()
def send_message(employee_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    if not role_permissions(user_role(user)).get("can_message_employees"):
        return warn("Warning: your HRMS role cannot use employee messages.")

    target_id = to_object_id(employee_id)
    if not target_id:
        return fail("Invalid employee id")
    target = employees_collection.find_one({"_id": target_id})
    own = employees_collection.find_one({"user_id": user["_id"]})
    if not own:
        return fail("Your employee profile is required before sending messages")
    if not target or not target.get("user_id"):
        return fail("Employee is not available for messaging", 404)
    if target["_id"] == own["_id"]:
        return fail("You cannot message yourself")
    if not can_open_message_thread(user, target):
        return warn("Warning: you can only message employees in your allowed department or team scope.")

    data = request.get_json() or {}
    body = (data.get("body") or "").strip()
    if not body:
        return fail("Message cannot be empty")
    now = datetime.now(timezone.utc)
    key = conversation_key_for(user["_id"], target["user_id"])
    result = hrms_messages_collection.insert_one({
        "conversation_key": key,
        "participant_user_ids": [user["_id"], target["user_id"]],
        "sender_user_id": user["_id"],
        "sender_employee_id": own["_id"],
        "receiver_user_id": target["user_id"],
        "receiver_employee_id": target["_id"],
        "body": body,
        "created_at": now,
        "updated_at": now,
        "read_by_user_ids": [user["_id"]],
    })
    return ok("Message sent", {"id": str(result.inserted_id), "conversation_key": key}, 201)
