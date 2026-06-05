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
    row, error = att.check_in(user, request.get_json() or {})
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
    row, error = att.check_out(user, request.get_json() or {})
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
    row, error = att.assign_manager(user, user_id, data.get("manager_user_id") or data.get("manager_id"))
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
    if not can_access_employee(user, employee_id):
        return warn("Warning: you can only create payroll for employees in your allowed department or team scope.")
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


@hrms_bp.get("/performance")
@jwt_required()
def list_performance_reviews():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    employee_ids = scoped_employee_ids(user)
    rows = list(performance_reviews_collection.find({"employee_id": {"$in": employee_ids}}).sort("created_at", -1).limit(100))
    return ok("Performance reviews fetched", {"reviews": [serialize_review(row) for row in rows]})


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
    if not can_access_employee(user, employee_id):
        return warn("Warning: you can only create reviews for employees in your allowed department or team scope.")
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
