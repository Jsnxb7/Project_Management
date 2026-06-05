from datetime import datetime, timedelta, timezone, time
from bson import ObjectId

from database.db import (
    users_collection,
    employees_collection,
    attendance_collection,
    leave_requests_collection,
    notifications_collection,
    hrms_attendance_rules_collection,
    hrms_manager_assignments_collection,
    hrms_attendance_reviews_collection,
    hrms_attendance_meetings_collection,
    hrms_attendance_corrections_collection,
    hrms_audit_logs_collection,
)
from services.role_access import user_role, role_permissions, normalize_role
from services.hrms_service import to_object_id, serialize_employee, scoped_employee_query

DEFAULT_RULES = {
    "start_time": "09:30",
    "late_after": "09:45",
    "end_time": "18:00",
    "minimum_full_day_minutes": 480,
    "minimum_half_day_minutes": 240,
    "overtime_after_minutes": 540,
    "working_days": ["mon", "tue", "wed", "thu", "fri"],
    "weekend_days": ["sat", "sun"],
    "holidays": [],
    "timezone": "Asia/Kolkata",
    "grace_minutes": 15,
    "auto_absent_after": "23:59",
    "allow_late_checkin": True,
    "allow_checkout_without_review": True,
}
MANAGERIAL_ROLES = {"Super User", "Management Admin", "HR Director", "HR Manager", "HR Business Partner", "Senior Manager"}
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else dt


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def day_key(value=None):
    dt = parse_date(value) or now_utc()
    return dt.date().isoformat()


def month_bounds(month=None):
    if month:
        base = datetime.strptime(month[:7] + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        today = now_utc()
        base = datetime(today.year, today.month, 1, tzinfo=timezone.utc)
    next_month = datetime(base.year + (base.month // 12), (base.month % 12) + 1, 1, tzinfo=timezone.utc)
    return base.date().isoformat(), (next_month - timedelta(days=1)).date().isoformat()


def time_minutes(value):
    try:
        h, m = str(value).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def minutes_since_midnight(dt):
    dt = parse_date(dt) or now_utc()
    return dt.hour * 60 + dt.minute


def get_rules():
    rules = hrms_attendance_rules_collection.find_one({"active": True}) or {}
    merged = {**DEFAULT_RULES, **{k: v for k, v in rules.items() if k != "_id"}}
    return merged


def save_rules(data, actor_id):
    allowed = set(DEFAULT_RULES.keys())
    updates = {k: data[k] for k in allowed if k in data}
    updates.update({"active": True, "updated_at": now_utc(), "updated_by": to_object_id(actor_id)})
    if not hrms_attendance_rules_collection.find_one({"active": True}):
        updates["created_at"] = now_utc()
        hrms_attendance_rules_collection.insert_one({**DEFAULT_RULES, **updates})
    else:
        hrms_attendance_rules_collection.update_one({"active": True}, {"$set": updates})
    audit(actor_id, "attendance_rules_updated", None, {}, updates)
    return get_rules()


def current_employee(user):
    return employees_collection.find_one({"user_id": user.get("_id")}) if user else None


def employee_user_id(employee):
    return employee.get("user_id") if employee else None


def is_working_day(date_str, rules=None):
    rules = rules or get_rules()
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    name = DAY_NAMES[dt.weekday()]
    if date_str[:10] in (rules.get("holidays") or []):
        return False
    return name in (rules.get("working_days") or [])


def can_manage_attendance_for(user, employee):
    if not user or not employee:
        return False
    role = user_role(user)
    perms = role_permissions(role)
    if perms.get("is_super_user") or perms.get("can_view_all_attendance"):
        return True
    if employee.get("manager_id") == user.get("_id"):
        return True
    own = current_employee(user)
    if own and employee.get("_id") == own.get("_id"):
        return True
    if perms.get("can_manage_employees"):
        return True
    return False


def team_employee_query(user):
    role = user_role(user)
    perms = role_permissions(role)
    if perms.get("is_super_user") or perms.get("can_view_all_attendance") or perms.get("can_view_company_dashboard"):
        return {}
    ids = []
    own = current_employee(user)
    if own:
        ids.append(own.get("_id"))
    ids.extend([e["_id"] for e in employees_collection.find({"manager_id": user.get("_id"), "employment_status": {"$ne": "Inactive"}}, {"_id": 1})])
    if perms.get("can_manage_employee_relations") or perms.get("can_manage_employees"):
        scoped = scoped_employee_query(user)
        ids.extend([e["_id"] for e in employees_collection.find(scoped, {"_id": 1})])
    return {"_id": {"$in": list({i for i in ids if i})}}


def serialize_attendance(row):
    if not row:
        return None
    employee = employees_collection.find_one({"_id": row.get("employee_id")})
    return {
        "id": str(row.get("_id")),
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "employee_name": employee.get("name") if employee else "Employee",
        "date": row.get("date_key") or day_key(row.get("date")),
        "check_in": iso(row.get("check_in")),
        "check_out": iso(row.get("check_out")),
        "worked_minutes": row.get("worked_minutes", 0),
        "expected_minutes": row.get("expected_minutes", 480),
        "working_hours": round((row.get("worked_minutes", 0) or 0) / 60, 2),
        "soft_tags": row.get("soft_tags", []),
        "hard_tags": row.get("hard_tags", []),
        "status": row.get("status", "present"),
        "manager_status": row.get("manager_status", "pending_review"),
        "manager_id": str(row.get("manager_id")) if row.get("manager_id") else None,
        "manager_note": row.get("manager_note", ""),
        "source": row.get("source", "system"),
    }


def serialize_leave(row):
    employee = employees_collection.find_one({"_id": row.get("employee_id")}) if row else None
    return {
        "id": str(row.get("_id")),
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "employee_name": employee.get("name") if employee else "Employee",
        "manager_id": str(row.get("manager_id")) if row.get("manager_id") else None,
        "leave_type": row.get("leave_type"),
        "start_date": row.get("start_date"),
        "end_date": row.get("end_date"),
        "days": row.get("days", 1),
        "reason": row.get("reason", ""),
        "status": row.get("status", "pending"),
        "manager_note": row.get("manager_note", ""),
        "reviewed_by": str(row.get("reviewed_by")) if row.get("reviewed_by") else None,
        "reviewed_at": iso(row.get("reviewed_at")),
        "created_at": iso(row.get("created_at")),
    }


def notify(user_id, message, level="Info", entity_type="attendance", entity_id=None):
    if not user_id:
        return
    notifications_collection.insert_one({
        "user_id": to_object_id(user_id),
        "message": message,
        "type": level,
        "category": "Attendance",
        "entity_type": entity_type,
        "entity_id": to_object_id(entity_id) if entity_id else None,
        "is_read": False,
        "created_at": now_utc(),
    })


def audit(actor_id, action, target_user_id=None, old_value=None, new_value=None, record_id=None):
    hrms_audit_logs_collection.insert_one({
        "actor_id": to_object_id(actor_id),
        "action": action,
        "target_user_id": to_object_id(target_user_id) if target_user_id else None,
        "record_id": to_object_id(record_id) if record_id else None,
        "old_value": old_value or {},
        "new_value": new_value or {},
        "created_at": now_utc(),
    })


def calculate_tags(check_in=None, check_out=None, status="present", rules=None):
    rules = rules or get_rules()
    tags = []
    worked = 0
    if check_in and minutes_since_midnight(check_in) > time_minutes(rules.get("late_after")):
        tags.append("late_checkin")
    if check_in and check_out:
        worked = int(max((parse_date(check_out) - parse_date(check_in)).total_seconds(), 0) / 60)
        if worked >= int(rules.get("overtime_after_minutes", 540)):
            tags.append("overtime")
        if worked < int(rules.get("minimum_half_day_minutes", 240)):
            tags.append("half_day")
        elif worked >= int(rules.get("minimum_full_day_minutes", 480)):
            tags.append("full_day")
        if minutes_since_midnight(check_out) < time_minutes(rules.get("end_time")) and worked < int(rules.get("minimum_full_day_minutes", 480)):
            tags.append("early_checkout")
    elif check_in and not check_out:
        tags.append("missing_checkout")
    if status == "absent":
        tags.append("absent")
    return list(dict.fromkeys(tags)), worked


def manager_for_employee(employee):
    if not employee:
        return None
    explicit = employee.get("manager_id")
    if explicit:
        return explicit
    role = normalize_role(employee.get("designation") or "Employee")
    if role in MANAGERIAL_ROLES and role != "Super User":
        su = users_collection.find_one({"$or": [{"hrms_role": "Super User"}, {"role": "Super User"}], "is_active": True})
        return su.get("_id") if su else None
    return None


def ensure_manager_assignments(actor_id=None):
    super_user = users_collection.find_one({"$or": [{"hrms_role": "Super User"}, {"role": "Super User"}], "is_active": True})
    super_user_id = super_user.get("_id") if super_user else None
    fixed = 0
    for employee in employees_collection.find({"employment_status": {"$ne": "Inactive"}}):
        user = users_collection.find_one({"_id": employee.get("user_id")}) if employee.get("user_id") else None
        role = user_role(user) if user else normalize_role(employee.get("designation") or "Employee")
        if role == "Super User" or not employee.get("user_id"):
            continue
        manager_id = employee.get("manager_id")
        if not manager_id and role in MANAGERIAL_ROLES and super_user_id:
            manager_id = super_user_id
        if manager_id:
            employees_collection.update_one({"_id": employee["_id"]}, {"$set": {"manager_id": manager_id, "manager_status": "assigned", "updated_at": now_utc()}})
            hrms_manager_assignments_collection.update_one(
                {"employee_user_id": employee.get("user_id"), "status": "active"},
                {"$set": {"manager_user_id": manager_id, "assigned_by": to_object_id(actor_id) if actor_id else super_user_id, "updated_at": now_utc(), "status": "active"}, "$setOnInsert": {"created_at": now_utc()}},
                upsert=True,
            )
            fixed += 1
        else:
            employees_collection.update_one({"_id": employee["_id"]}, {"$set": {"manager_status": "missing", "updated_at": now_utc()}})
            if super_user_id:
                notify(super_user_id, f"{employee.get('name', 'Employee')} does not have a manager assigned.", "Warning", "manager_assignment", employee.get("_id"))
    return fixed


def check_in(user, data=None):
    data = data or {}
    employee = current_employee(user)
    if not employee:
        return None, "Employee profile is required before attendance can be recorded"
    rules = get_rules()
    now = parse_date(data.get("check_in")) or now_utc()
    key = day_key(now)
    existing = attendance_collection.find_one({"employee_id": employee["_id"], "date_key": key})
    if existing and existing.get("check_in"):
        return serialize_attendance(existing), "Already checked in today"
    manager_id = manager_for_employee(employee)
    tags, worked = calculate_tags(check_in=now, rules=rules)
    record = {
        "user_id": employee.get("user_id"),
        "employee_id": employee["_id"],
        "department": employee.get("department"),
        "date": datetime.strptime(key, "%Y-%m-%d").replace(tzinfo=timezone.utc),
        "date_key": key,
        "check_in": now,
        "check_out": None,
        "worked_minutes": 0,
        "expected_minutes": int(rules.get("minimum_full_day_minutes", 480)),
        "soft_tags": tags,
        "hard_tags": [],
        "status": "checked_in",
        "manager_status": "pending_review" if tags else "normal",
        "manager_id": manager_id,
        "source": "self_checkin",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "created_by": user.get("_id"),
    }
    if existing:
        attendance_collection.update_one({"_id": existing["_id"]}, {"$set": record})
        inserted_id = existing["_id"]
    else:
        inserted_id = attendance_collection.insert_one(record).inserted_id
    notify(user.get("_id"), "Check-in recorded successfully.", "Success", "attendance", inserted_id)
    if tags and manager_id:
        notify(manager_id, f"{employee.get('name')} has attendance tags: {', '.join(tags)}.", "Warning", "attendance", inserted_id)
    audit(user.get("_id"), "attendance_check_in", user.get("_id"), {}, record, inserted_id)
    return serialize_attendance(attendance_collection.find_one({"_id": inserted_id})), None


def check_out(user, data=None):
    data = data or {}
    employee = current_employee(user)
    if not employee:
        return None, "Employee profile is required before attendance can be recorded"
    now = parse_date(data.get("check_out")) or now_utc()
    key = day_key(now)
    record = attendance_collection.find_one({"employee_id": employee["_id"], "date_key": key})
    if not record or not record.get("check_in"):
        return None, "Please check in before checking out"
    if record.get("check_out"):
        return serialize_attendance(record), "Already checked out today"
    rules = get_rules()
    tags, worked = calculate_tags(record.get("check_in"), now, rules=rules)
    tags = list(dict.fromkeys((record.get("soft_tags") or []) + tags))
    status = "present" if worked >= int(rules.get("minimum_half_day_minutes", 240)) else "half_day"
    update = {"check_out": now, "worked_minutes": worked, "soft_tags": tags, "status": status, "manager_status": "pending_review" if tags else "normal", "updated_at": now_utc()}
    attendance_collection.update_one({"_id": record["_id"]}, {"$set": update})
    notify(user.get("_id"), "Checkout recorded successfully.", "Success", "attendance", record["_id"])
    if tags and record.get("manager_id"):
        notify(record.get("manager_id"), f"{employee.get('name')} checked out with tags: {', '.join(tags)}.", "Warning", "attendance", record["_id"])
    audit(user.get("_id"), "attendance_check_out", user.get("_id"), serialize_attendance(record), update, record["_id"])
    return serialize_attendance(attendance_collection.find_one({"_id": record["_id"]})), None


def date_range(start, end):
    s = datetime.strptime(start[:10], "%Y-%m-%d").date()
    e = datetime.strptime(end[:10], "%Y-%m-%d").date()
    while s <= e:
        yield s.isoformat()
        s += timedelta(days=1)


def approved_leave_for(employee_id, date_key):
    return leave_requests_collection.find_one({
        "employee_id": employee_id,
        "status": "approved",
        "start_date": {"$lte": date_key},
        "end_date": {"$gte": date_key},
    })


def sync_absences_for_user(user, start=None, end=None):
    rules = get_rules()
    start = start or month_bounds()[0]
    end = end or now_utc().date().isoformat()
    employee_ids = [e["_id"] for e in employees_collection.find(team_employee_query(user), {"_id": 1})]
    for key in date_range(start, end):
        if key > now_utc().date().isoformat() or not is_working_day(key, rules):
            continue
        for employee in employees_collection.find({"_id": {"$in": employee_ids}, "employment_status": {"$ne": "Inactive"}}):
            if attendance_collection.find_one({"employee_id": employee["_id"], "date_key": key}):
                continue
            leave = approved_leave_for(employee["_id"], key)
            manager_id = manager_for_employee(employee)
            if leave:
                attendance_collection.insert_one({
                    "user_id": employee.get("user_id"), "employee_id": employee["_id"], "department": employee.get("department"),
                    "date": datetime.strptime(key, "%Y-%m-%d").replace(tzinfo=timezone.utc), "date_key": key,
                    "check_in": None, "check_out": None, "worked_minutes": 0, "expected_minutes": int(rules.get("minimum_full_day_minutes", 480)),
                    "soft_tags": ["leave_approved"], "hard_tags": ["leave_approved"], "status": "leave", "manager_status": "approved",
                    "manager_id": manager_id, "source": "leave_sync", "created_at": now_utc(), "updated_at": now_utc(),
                })
            else:
                attendance_collection.insert_one({
                    "user_id": employee.get("user_id"), "employee_id": employee["_id"], "department": employee.get("department"),
                    "date": datetime.strptime(key, "%Y-%m-%d").replace(tzinfo=timezone.utc), "date_key": key,
                    "check_in": None, "check_out": None, "worked_minutes": 0, "expected_minutes": int(rules.get("minimum_full_day_minutes", 480)),
                    "soft_tags": ["absent"], "hard_tags": [], "status": "absent", "manager_status": "pending_review",
                    "manager_id": manager_id, "source": "auto_absent", "created_at": now_utc(), "updated_at": now_utc(),
                })
                if employee.get("user_id"):
                    notify(employee.get("user_id"), f"You were soft-marked absent for {key}. Request correction if needed.", "Warning", "attendance")
                if manager_id:
                    notify(manager_id, f"{employee.get('name')} was soft-marked absent for {key}.", "Warning", "attendance")


def list_attendance(user, employee_id=None, start=None, end=None):
    start = start or month_bounds()[0]
    end = end or month_bounds()[1]
    sync_absences_for_user(user, start, min(end, now_utc().date().isoformat()))
    base = {"date_key": {"$gte": start, "$lte": end}}
    query = team_employee_query(user)
    allowed_ids = [e["_id"] for e in employees_collection.find(query, {"_id": 1})]
    if employee_id:
        emp_obj = to_object_id(employee_id)
        if emp_obj not in allowed_ids:
            return []
        base["employee_id"] = emp_obj
    else:
        base["employee_id"] = {"$in": allowed_ids}
    return [serialize_attendance(r) for r in attendance_collection.find(base).sort("date_key", -1).limit(500)]


def calendar_payload(user, employee_id=None, month=None):
    start, end = month_bounds(month)
    rows = list_attendance(user, employee_id, start, end)
    leave_base = {"start_date": {"$lte": end}, "end_date": {"$gte": start}}
    if employee_id:
        leave_base["employee_id"] = to_object_id(employee_id)
    else:
        ids = [e["_id"] for e in employees_collection.find(team_employee_query(user), {"_id": 1})]
        leave_base["employee_id"] = {"$in": ids}
    leaves = [serialize_leave(l) for l in leave_requests_collection.find(leave_base).sort("start_date", 1)]
    return {"start": start, "end": end, "records": rows, "leaves": leaves, "rules": get_rules()}


def request_leave(user, data):
    employee = current_employee(user)
    if not employee:
        return None, "Employee profile is required before requesting leave"
    start = (data.get("start_date") or "")[:10]
    end = (data.get("end_date") or start)[:10]
    if not start:
        return None, "Start date is required"
    if end < start:
        return None, "End date cannot be before start date"
    manager_id = manager_for_employee(employee)
    days = sum(1 for _ in date_range(start, end))
    record = {
        "user_id": employee.get("user_id"), "employee_id": employee["_id"], "manager_id": manager_id,
        "leave_type": data.get("leave_type") or "casual_leave", "start_date": start, "end_date": end, "days": days,
        "reason": data.get("reason") or "", "status": "pending", "manager_note": "", "reviewed_by": None, "reviewed_at": None,
        "created_at": now_utc(), "updated_at": now_utc(), "created_by": user.get("_id"),
    }
    inserted = leave_requests_collection.insert_one(record).inserted_id
    for key in date_range(start, end):
        attendance_collection.update_one(
            {"employee_id": employee["_id"], "date_key": key, "status": {"$ne": "leave"}},
            {"$addToSet": {"soft_tags": "leave_pending"}, "$set": {"manager_status": "leave_pending", "updated_at": now_utc()}},
            upsert=False,
        )
    notify(user.get("_id"), "Leave request submitted.", "Info", "leave", inserted)
    if manager_id:
        notify(manager_id, f"{employee.get('name')} requested leave from {start} to {end}.", "Info", "leave", inserted)
    audit(user.get("_id"), "leave_requested", user.get("_id"), {}, record, inserted)
    return serialize_leave(leave_requests_collection.find_one({"_id": inserted})), None


def review_leave(user, leave_id, action, note=""):
    obj = to_object_id(leave_id)
    row = leave_requests_collection.find_one({"_id": obj}) if obj else None
    if not row:
        return None, "Leave request not found"
    employee = employees_collection.find_one({"_id": row.get("employee_id")})
    if not can_manage_attendance_for(user, employee):
        return None, "You cannot review this leave request"
    status = "approved" if action == "approve" else "rejected"
    update = {"status": status, "manager_note": note, "reviewed_by": user.get("_id"), "reviewed_at": now_utc(), "updated_at": now_utc()}
    leave_requests_collection.update_one({"_id": obj}, {"$set": update})
    for key in date_range(row.get("start_date"), row.get("end_date")):
        if status == "approved":
            attendance_collection.update_one(
                {"employee_id": row.get("employee_id"), "date_key": key},
                {"$set": {"status": "leave", "manager_status": "approved", "manager_id": user.get("_id"), "updated_at": now_utc()}, "$addToSet": {"soft_tags": "leave_approved", "hard_tags": "leave_approved"}},
                upsert=True,
            )
        else:
            attendance_collection.update_one({"employee_id": row.get("employee_id"), "date_key": key}, {"$pull": {"soft_tags": "leave_pending"}, "$addToSet": {"soft_tags": "leave_rejected"}, "$set": {"manager_status": "review_required", "updated_at": now_utc()}})
    notify(row.get("user_id"), f"Your leave request was {status}.", "Success" if status == "approved" else "Warning", "leave", obj)
    audit(user.get("_id"), f"leave_{status}", row.get("user_id"), serialize_leave(row), update, obj)
    return serialize_leave(leave_requests_collection.find_one({"_id": obj})), None


def pending_leave_for_manager(user):
    ids = [e["_id"] for e in employees_collection.find(team_employee_query(user), {"_id": 1})]
    return [serialize_leave(l) for l in leave_requests_collection.find({"employee_id": {"$in": ids}, "status": "pending"}).sort("created_at", -1).limit(200)]


def review_attendance(user, attendance_id, action, note="", tags=None, overrides=None):
    obj = to_object_id(attendance_id)
    row = attendance_collection.find_one({"_id": obj}) if obj else None
    if not row:
        return None, "Attendance record not found"
    employee = employees_collection.find_one({"_id": row.get("employee_id")})
    if not can_manage_attendance_for(user, employee):
        return None, "You cannot review this attendance record"
    action_map = {
        "confirm_late": "confirmed_late", "confirm_absent": "confirmed_absent", "confirm_overtime": "confirmed_overtime",
        "excuse_late": "excused_late", "excuse_absence": "excused_absence", "confirm_present": "confirmed_present",
    }
    confirmed = tags or ([action_map[action]] if action in action_map else [])
    update = {"manager_status": "confirmed" if action.startswith("confirm") else "excused", "manager_note": note, "reviewed_by": user.get("_id"), "reviewed_at": now_utc(), "updated_at": now_utc()}
    if overrides:
        if "check_in" in overrides:
            update["check_in"] = parse_date(overrides.get("check_in"))
        if "check_out" in overrides:
            update["check_out"] = parse_date(overrides.get("check_out"))
        if update.get("check_in") and update.get("check_out"):
            new_tags, worked = calculate_tags(update["check_in"], update["check_out"])
            update["worked_minutes"] = worked
            update["soft_tags"] = new_tags
            update["status"] = "present"
    attendance_collection.update_one({"_id": obj}, {"$set": update, "$addToSet": {"hard_tags": {"$each": confirmed}}})
    hrms_attendance_reviews_collection.insert_one({
        "attendance_id": obj, "employee_user_id": employee.get("user_id") if employee else None, "reviewed_by": user.get("_id"),
        "review_action": action, "previous_tags": row.get("soft_tags", []), "confirmed_tags": confirmed, "note": note, "created_at": now_utc(),
    })
    if employee and employee.get("user_id"):
        notify(employee.get("user_id"), f"Your attendance record for {row.get('date_key')} was reviewed: {action}.", "Info", "attendance", obj)
    audit(user.get("_id"), f"attendance_{action}", employee.get("user_id") if employee else None, serialize_attendance(row), update, obj)
    return serialize_attendance(attendance_collection.find_one({"_id": obj})), None


def pending_reviews(user):
    ids = [e["_id"] for e in employees_collection.find(team_employee_query(user), {"_id": 1})]
    rows = attendance_collection.find({"employee_id": {"$in": ids}, "manager_status": {"$in": ["pending_review", "review_required"]}}).sort("date_key", -1).limit(200)
    return [serialize_attendance(r) for r in rows]


def assign_manager(actor, employee_user_id, manager_user_id):
    perms = role_permissions(user_role(actor))
    if not perms.get("is_super_user"):
        return None, "Only Super User can assign or overwrite managers"
    emp_user = to_object_id(employee_user_id)
    mgr_user = to_object_id(manager_user_id)
    if not emp_user or not mgr_user:
        return None, "Valid employee and manager users are required"
    employee = employees_collection.find_one({"user_id": emp_user})
    manager = users_collection.find_one({"_id": mgr_user})
    if not employee or not manager:
        return None, "Employee or manager not found"
    old = {"manager_id": employee.get("manager_id")}
    employees_collection.update_one({"_id": employee["_id"]}, {"$set": {"manager_id": mgr_user, "manager_status": "assigned", "updated_at": now_utc()}})
    hrms_manager_assignments_collection.update_one({"employee_user_id": emp_user, "status": "active"}, {"$set": {"manager_user_id": mgr_user, "assigned_by": actor.get("_id"), "status": "active", "updated_at": now_utc()}, "$setOnInsert": {"created_at": now_utc()}}, upsert=True)
    notify(emp_user, "Your reporting manager was updated.", "Info", "manager_assignment", employee["_id"])
    notify(mgr_user, f"{employee.get('name')} was assigned to you as a report.", "Info", "manager_assignment", employee["_id"])
    audit(actor.get("_id"), "manager_assigned", emp_user, old, {"manager_id": mgr_user}, employee["_id"])
    return serialize_employee(employees_collection.find_one({"_id": employee["_id"]})), None


def manager_options(user):
    perms = role_permissions(user_role(user))
    if not perms.get("is_super_user") and not perms.get("can_manage_employees"):
        return []
    users = users_collection.find({"is_active": True, "$or": [{"hrms_role": {"$in": list(MANAGERIAL_ROLES)}}, {"role": {"$in": list(MANAGERIAL_ROLES)}}]}).sort("name", 1)
    return [{"user_id": str(u["_id"]), "name": u.get("name") or u.get("email"), "role": user_role(u), "email": u.get("email")} for u in users]


def create_meeting(user, data):
    employee = employees_collection.find_one({"_id": to_object_id(data.get("employee_id"))})
    if not can_manage_attendance_for(user, employee):
        return None, "You cannot schedule a meeting for this employee"
    record = {
        "employee_user_id": employee.get("user_id"), "employee_id": employee.get("_id"), "manager_user_id": user.get("_id"),
        "linked_attendance_id": to_object_id(data.get("attendance_id")), "linked_leave_request_id": to_object_id(data.get("leave_id")),
        "title": data.get("title") or "Attendance Review Meeting", "reason": data.get("reason") or "Attendance discussion",
        "meeting_date": (data.get("meeting_date") or now_utc().date().isoformat())[:10], "meeting_time": data.get("meeting_time") or "10:00",
        "description": data.get("description") or "", "status": "scheduled", "created_at": now_utc(), "updated_at": now_utc(),
    }
    inserted = hrms_attendance_meetings_collection.insert_one(record).inserted_id
    notify(employee.get("user_id"), f"Attendance meeting scheduled on {record['meeting_date']} at {record['meeting_time']}.", "Info", "attendance_meeting", inserted)
    audit(user.get("_id"), "attendance_meeting_scheduled", employee.get("user_id"), {}, record, inserted)
    return serialize_meeting(hrms_attendance_meetings_collection.find_one({"_id": inserted})), None


def serialize_meeting(row):
    employee = employees_collection.find_one({"_id": row.get("employee_id")}) if row else None
    return {"id": str(row.get("_id")), "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None, "employee_name": employee.get("name") if employee else "Employee", "title": row.get("title"), "reason": row.get("reason"), "meeting_date": row.get("meeting_date"), "meeting_time": row.get("meeting_time"), "description": row.get("description", ""), "status": row.get("status", "scheduled")}


def list_meetings(user):
    ids = [e["_id"] for e in employees_collection.find(team_employee_query(user), {"_id": 1})]
    own = current_employee(user)
    q = {"$or": [{"employee_id": {"$in": ids}}, {"manager_user_id": user.get("_id")}]}
    if own:
        q["$or"].append({"employee_id": own["_id"]})
    return [serialize_meeting(m) for m in hrms_attendance_meetings_collection.find(q).sort("meeting_date", -1).limit(100)]


def update_meeting(user, meeting_id, status):
    obj = to_object_id(meeting_id)
    row = hrms_attendance_meetings_collection.find_one({"_id": obj}) if obj else None
    if not row:
        return None, "Meeting not found"
    employee = employees_collection.find_one({"_id": row.get("employee_id")})
    if not can_manage_attendance_for(user, employee):
        return None, "You cannot update this meeting"
    hrms_attendance_meetings_collection.update_one({"_id": obj}, {"$set": {"status": status, "updated_at": now_utc()}})
    audit(user.get("_id"), f"attendance_meeting_{status}", employee.get("user_id") if employee else None, serialize_meeting(row), {"status": status}, obj)
    return serialize_meeting(hrms_attendance_meetings_collection.find_one({"_id": obj})), None


def request_correction(user, data):
    employee = current_employee(user)
    if not employee:
        return None, "Employee profile is required"
    record = {
        "employee_id": employee["_id"], "employee_user_id": user.get("_id"), "manager_id": manager_for_employee(employee),
        "attendance_id": to_object_id(data.get("attendance_id")), "date_key": (data.get("date") or now_utc().date().isoformat())[:10],
        "requested_check_in": parse_date(data.get("requested_check_in")), "requested_check_out": parse_date(data.get("requested_check_out")),
        "reason": data.get("reason") or "Attendance correction requested", "status": "pending", "manager_note": "",
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    inserted = hrms_attendance_corrections_collection.insert_one(record).inserted_id
    if record.get("manager_id"):
        notify(record.get("manager_id"), f"{employee.get('name')} requested attendance correction.", "Info", "attendance_correction", inserted)
    audit(user.get("_id"), "attendance_correction_requested", user.get("_id"), {}, record, inserted)
    return serialize_correction(hrms_attendance_corrections_collection.find_one({"_id": inserted})), None


def serialize_correction(row):
    employee = employees_collection.find_one({"_id": row.get("employee_id")}) if row else None
    return {"id": str(row.get("_id")), "employee_id": str(row.get("employee_id")), "employee_name": employee.get("name") if employee else "Employee", "date": row.get("date_key"), "requested_check_in": iso(row.get("requested_check_in")), "requested_check_out": iso(row.get("requested_check_out")), "reason": row.get("reason"), "status": row.get("status"), "manager_note": row.get("manager_note", "")}


def list_corrections(user):
    ids = [e["_id"] for e in employees_collection.find(team_employee_query(user), {"_id": 1})]
    return [serialize_correction(c) for c in hrms_attendance_corrections_collection.find({"employee_id": {"$in": ids}}).sort("created_at", -1).limit(100)]
