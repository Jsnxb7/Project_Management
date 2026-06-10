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
from services.hrms_service import to_object_id, serialize_employee, scoped_employee_query, employee_manager_ids

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


def server_now():
    # Attendance punches must use the backend server clock, not browser-submitted time.
    return datetime.now().astimezone()


def iso(dt):
    return dt.isoformat() if dt and hasattr(dt, "isoformat") else dt


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone() if value.tzinfo else value.astimezone()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def comparable_datetime(value):
    dt = parse_date(value)
    if not dt:
        return None
    return dt.astimezone() if dt.tzinfo else dt.astimezone()


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


def is_assigned_attendance_manager(user, employee):
    if not user or not employee:
        return False
    user_id = user.get("_id")
    return user_id in employee_manager_ids(employee)


def can_manage_attendance_for(user, employee):
    if not user or not employee:
        return False
    perms = role_permissions(user_role(user))
    # Super User can override all attendance. Other users can modify/verify only
    # employees explicitly assigned to them as reporting managers.
    return bool(perms.get("is_super_user") or is_assigned_attendance_manager(user, employee))


def team_employee_query(user):
    role = user_role(user)
    perms = role_permissions(role)
    if perms.get("is_super_user"):
        return {}
    ids = []
    own = current_employee(user)
    if own:
        ids.append(own.get("_id"))
    ids.extend([e["_id"] for e in employees_collection.find({
        "$or": [{"manager_id": user.get("_id")}, {"manager_ids": user.get("_id")}],
        "employment_status": {"$ne": "Inactive"},
    }, {"_id": 1})])
    return {"_id": {"$in": list({i for i in ids if i})}}


def serialize_attendance(row):
    if not row:
        return None
    employee = employees_collection.find_one({"_id": row.get("employee_id")})
    manager_ids = employee_manager_ids(employee) if employee else []
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
        "manager_id": str(row.get("manager_id") or (manager_ids[0] if manager_ids else None)) if (row.get("manager_id") or manager_ids) else None,
        "manager_ids": [str(mid) for mid in (row.get("manager_ids") or manager_ids or [])],
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
        "manager_ids": [str(mid) for mid in (row.get("manager_ids") or [])],
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


def calculate_tags(check_in=None, check_out=None, status="present", rules=None, mark_missing_checkout=True):
    rules = rules or get_rules()
    tags = []
    worked = 0
    if check_in and minutes_since_midnight(check_in) > time_minutes(rules.get("late_after")):
        tags.append("late_checkin")
    if check_in and check_out:
        check_in_dt = comparable_datetime(check_in)
        check_out_dt = comparable_datetime(check_out)
        worked = int(max((check_out_dt - check_in_dt).total_seconds(), 0) / 60) if check_in_dt and check_out_dt else 0
        if worked >= int(rules.get("overtime_after_minutes", 540)):
            tags.append("overtime")
        if worked < int(rules.get("minimum_half_day_minutes", 240)):
            tags.append("half_day")
        elif worked >= int(rules.get("minimum_full_day_minutes", 480)):
            tags.append("full_day")
        if minutes_since_midnight(check_out) < time_minutes(rules.get("end_time")) and worked < int(rules.get("minimum_full_day_minutes", 480)):
            tags.append("early_checkout")
    elif mark_missing_checkout and check_in and not check_out:
        tags.append("missing_checkout")
    if status == "absent":
        tags.append("absent")
    return list(dict.fromkeys(tags)), worked


def managers_for_employee(employee):
    if not employee:
        return []
    explicit = employee_manager_ids(employee)
    if explicit:
        return explicit
    employee_user_id = employee.get("user_id")
    role = "Employee"
    if employee_user_id:
        linked_user = users_collection.find_one({"_id": employee_user_id})
        role = user_role(linked_user) if linked_user else role
    role = normalize_role(role or employee.get("designation") or "Employee")
    if role in MANAGERIAL_ROLES:
        return [u["_id"] for u in users_collection.find({"$or": [{"hrms_role": "Super User"}, {"role": "Super User"}], "is_active": True}, {"_id": 1}) if u.get("_id") != employee_user_id]
    return []


def manager_for_employee(employee):
    manager_ids = managers_for_employee(employee)
    return manager_ids[0] if manager_ids else None


def notify_managers(manager_ids, message, level="Info", entity_type="attendance", entity_id=None):
    for manager_id in manager_ids or []:
        notify(manager_id, message, level, entity_type, entity_id)


def ensure_manager_assignments(actor_id=None):
    super_users = list(users_collection.find({"$or": [{"hrms_role": "Super User"}, {"role": "Super User"}], "is_active": True}, {"_id": 1, "name": 1, "email": 1}))
    super_user_ids = [u["_id"] for u in super_users]
    default_super_id = super_user_ids[0] if super_user_ids else None
    fixed = 0
    for employee in employees_collection.find({"employment_status": {"$ne": "Inactive"}}):
        user = users_collection.find_one({"_id": employee.get("user_id")}) if employee.get("user_id") else None
        role = user_role(user) if user else normalize_role(employee.get("designation") or "Employee")
        current_ids = employee_manager_ids(employee)
        desired_ids = list(current_ids)

        if role == "Super User":
            # Auto-pair Super Users with the other active Super User(s), e.g. spur1 -> spur2 and spur2 -> spur1.
            desired_ids = [sid for sid in super_user_ids if sid != employee.get("user_id")]
        elif role in MANAGERIAL_ROLES:
            desired_ids = [sid for sid in super_user_ids if sid != employee.get("user_id")] or ([default_super_id] if default_super_id else [])

        desired_ids = list(dict.fromkeys([mid for mid in desired_ids if mid]))
        if desired_ids:
            employees_collection.update_one({"_id": employee["_id"]}, {"$set": {"manager_id": desired_ids[0], "manager_ids": desired_ids, "manager_status": "assigned", "updated_at": now_utc()}})
            hrms_manager_assignments_collection.update_many({"employee_user_id": employee.get("user_id")}, {"$set": {"status": "inactive", "updated_at": now_utc()}})
            for manager_id in desired_ids:
                hrms_manager_assignments_collection.update_one(
                    {"employee_user_id": employee.get("user_id"), "manager_user_id": manager_id},
                    {"$set": {"assigned_by": to_object_id(actor_id) if actor_id else default_super_id, "updated_at": now_utc(), "status": "active"}, "$setOnInsert": {"created_at": now_utc()}},
                    upsert=True,
                )
            fixed += 1
        else:
            employees_collection.update_one({"_id": employee["_id"]}, {"$set": {"manager_status": "missing", "manager_ids": [], "manager_id": None, "updated_at": now_utc()}})
            if default_super_id:
                notify(default_super_id, f"{employee.get('name', 'Employee')} does not have a manager assigned.", "Warning", "manager_assignment", employee.get("_id"))
    return fixed


def check_in(user, data=None):
    data = data or {}
    employee = current_employee(user)
    if not employee:
        return None, "Employee profile is required before attendance can be recorded"
    rules = get_rules()
    now = server_now()
    key = day_key(now)
    existing = attendance_collection.find_one({"employee_id": employee["_id"], "date_key": key})
    if existing and existing.get("check_in"):
        return serialize_attendance(existing), "Already checked in today"
    manager_ids = managers_for_employee(employee)
    manager_id = manager_ids[0] if manager_ids else None
    tags, worked = calculate_tags(check_in=now, rules=rules, mark_missing_checkout=False)
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
        "manager_ids": manager_ids,
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
    if tags and manager_ids:
        notify_managers(manager_ids, f"{employee.get('name')} has attendance tags: {', '.join(tags)}.", "Warning", "attendance", inserted_id)
    audit(user.get("_id"), "attendance_check_in", user.get("_id"), {}, record, inserted_id)
    return serialize_attendance(attendance_collection.find_one({"_id": inserted_id})), None


def check_out(user, data=None):
    data = data or {}
    employee = current_employee(user)
    if not employee:
        return None, "Employee profile is required before attendance can be recorded"
    now = server_now()
    key = day_key(now)
    record = attendance_collection.find_one({"employee_id": employee["_id"], "date_key": key})
    if not record or not record.get("check_in"):
        return None, "Please check in before checking out"
    if record.get("check_out"):
        return serialize_attendance(record), "Already checked out today"
    rules = get_rules()
    tags, worked = calculate_tags(record.get("check_in"), now, rules=rules)
    prior_tags = [tag for tag in (record.get("soft_tags") or []) if tag != "missing_checkout"]
    tags = list(dict.fromkeys(prior_tags + tags))
    status = "present" if worked >= int(rules.get("minimum_half_day_minutes", 240)) else "half_day"
    update = {"check_out": now, "worked_minutes": worked, "soft_tags": tags, "status": status, "manager_status": "pending_review" if tags else "normal", "updated_at": now_utc()}
    attendance_collection.update_one({"_id": record["_id"]}, {"$set": update})
    notify(user.get("_id"), "Checkout recorded successfully.", "Success", "attendance", record["_id"])
    manager_ids = record.get("manager_ids") or managers_for_employee(employee)
    if tags and manager_ids:
        notify_managers(manager_ids, f"{employee.get('name')} checked out with tags: {', '.join(tags)}.", "Warning", "attendance", record["_id"])
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
            manager_ids = managers_for_employee(employee)
            manager_id = manager_ids[0] if manager_ids else None
            if leave:
                attendance_collection.insert_one({
                    "user_id": employee.get("user_id"), "employee_id": employee["_id"], "department": employee.get("department"),
                    "date": datetime.strptime(key, "%Y-%m-%d").replace(tzinfo=timezone.utc), "date_key": key,
                    "check_in": None, "check_out": None, "worked_minutes": 0, "expected_minutes": int(rules.get("minimum_full_day_minutes", 480)),
                    "soft_tags": ["leave_approved"], "hard_tags": ["leave_approved"], "status": "leave", "manager_status": "approved",
                    "manager_id": manager_id, "manager_ids": manager_ids, "source": "leave_sync", "created_at": now_utc(), "updated_at": now_utc(),
                })
            else:
                attendance_collection.insert_one({
                    "user_id": employee.get("user_id"), "employee_id": employee["_id"], "department": employee.get("department"),
                    "date": datetime.strptime(key, "%Y-%m-%d").replace(tzinfo=timezone.utc), "date_key": key,
                    "check_in": None, "check_out": None, "worked_minutes": 0, "expected_minutes": int(rules.get("minimum_full_day_minutes", 480)),
                    "soft_tags": ["absent"], "hard_tags": [], "status": "absent", "manager_status": "pending_review",
                    "manager_id": manager_id, "manager_ids": manager_ids, "source": "auto_absent", "created_at": now_utc(), "updated_at": now_utc(),
                })
                if employee.get("user_id"):
                    notify(employee.get("user_id"), f"You were soft-marked absent for {key}. Request correction if needed.", "Warning", "attendance")
                if manager_ids:
                    notify_managers(manager_ids, f"{employee.get('name')} was soft-marked absent for {key}.", "Warning", "attendance")


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


def calendar_record_summary(row):
    if not row:
        return None
    return {
        "employee_id": row.get("employee_id"),
        "employee_name": row.get("employee_name"),
        "date": row.get("date"),
        "worked_minutes": row.get("worked_minutes", 0),
        "soft_tags": row.get("soft_tags", []),
        "hard_tags": row.get("hard_tags", []),
        "status": row.get("status", "present"),
        "manager_status": row.get("manager_status", "pending_review"),
    }


def calendar_payload(user, employee_id=None, month=None, summary_only=False):
    start, end = month_bounds(month)
    rows = list_attendance(user, employee_id, start, end)
    leave_base = {"start_date": {"$lte": end}, "end_date": {"$gte": start}}
    if employee_id:
        leave_base["employee_id"] = to_object_id(employee_id)
    else:
        ids = [e["_id"] for e in employees_collection.find(team_employee_query(user), {"_id": 1})]
        leave_base["employee_id"] = {"$in": ids}
    leaves = [serialize_leave(l) for l in leave_requests_collection.find(leave_base).sort("start_date", 1)]
    return {"start": start, "end": end, "records": [calendar_record_summary(r) for r in rows] if summary_only else rows, "leaves": leaves, "rules": get_rules()}


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
    manager_ids = managers_for_employee(employee)
    manager_id = manager_ids[0] if manager_ids else None
    days = sum(1 for _ in date_range(start, end))
    record = {
        "user_id": employee.get("user_id"), "employee_id": employee["_id"], "manager_id": manager_id, "manager_ids": manager_ids,
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
    if manager_ids:
        notify_managers(manager_ids, f"{employee.get('name')} requested leave from {start} to {end}.", "Info", "leave", inserted)
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
                {"$set": {"status": "leave", "manager_status": "approved", "manager_id": user.get("_id"), "manager_ids": managers_for_employee(employee), "updated_at": now_utc()}, "$addToSet": {"soft_tags": "leave_approved", "hard_tags": "leave_approved"}},
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
            update["check_in"] = parse_date(overrides.get("check_in")) if overrides.get("check_in") else None
        if "check_out" in overrides:
            update["check_out"] = parse_date(overrides.get("check_out")) if overrides.get("check_out") else None
        effective_check_in = update["check_in"] if "check_in" in update else row.get("check_in")
        effective_check_out = update["check_out"] if "check_out" in update else row.get("check_out")
        if effective_check_in and effective_check_out:
            new_tags, worked = calculate_tags(effective_check_in, effective_check_out)
            update["worked_minutes"] = worked
            update["soft_tags"] = new_tags
            update["status"] = "present"
        elif effective_check_in and not effective_check_out:
            update["worked_minutes"] = 0
            update["soft_tags"] = ["missing_checkout"]
            update["status"] = "checked_in"
        elif not effective_check_in and not effective_check_out and action == "confirm_absent":
            update["worked_minutes"] = 0
            update["soft_tags"] = ["absent"]
            update["status"] = "absent"
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


def normalize_manager_id_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        raw = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = [value]
    ids = []
    for item in raw:
        obj = to_object_id(item)
        if obj and obj not in ids:
            ids.append(obj)
    return ids


def assign_manager(actor, employee_user_id, manager_user_id=None, manager_user_ids=None):
    perms = role_permissions(user_role(actor))
    if not perms.get("is_super_user"):
        return None, "Only Super User can assign or overwrite managers"
    emp_user = to_object_id(employee_user_id)
    mgr_users = normalize_manager_id_list(manager_user_ids if manager_user_ids is not None else manager_user_id)
    if not emp_user:
        return None, "Valid employee user is required"
    employee = employees_collection.find_one({"user_id": emp_user})
    if not employee:
        return None, "Employee not found"
    old = {"manager_id": employee.get("manager_id"), "manager_ids": employee.get("manager_ids") or []}
    if not mgr_users:
        employees_collection.update_one({"_id": employee["_id"]}, {"$set": {"manager_id": None, "manager_ids": [], "manager_status": "missing", "updated_at": now_utc()}})
        hrms_manager_assignments_collection.update_many({"employee_user_id": emp_user}, {"$set": {"status": "inactive", "updated_at": now_utc()}})
        notify(emp_user, "Your reporting manager assignment was updated.", "Info", "manager_assignment", employee["_id"])
        audit(actor.get("_id"), "managers_removed", emp_user, old, {"manager_ids": []}, employee["_id"])
        return serialize_employee(employees_collection.find_one({"_id": employee["_id"]})), None
    managers = list(users_collection.find({"_id": {"$in": mgr_users}, "is_active": True}))
    valid_manager_ids = {m["_id"] for m in managers}
    valid_ids = [manager_id for manager_id in mgr_users if manager_id in valid_manager_ids]
    if not valid_ids:
        return None, "Manager not found"
    employees_collection.update_one({"_id": employee["_id"]}, {"$set": {"manager_id": valid_ids[0], "manager_ids": valid_ids, "manager_status": "assigned", "updated_at": now_utc()}})
    hrms_manager_assignments_collection.update_many({"employee_user_id": emp_user}, {"$set": {"status": "inactive", "updated_at": now_utc()}})
    for manager_id in valid_ids:
        hrms_manager_assignments_collection.update_one({"employee_user_id": emp_user, "manager_user_id": manager_id}, {"$set": {"assigned_by": actor.get("_id"), "status": "active", "updated_at": now_utc()}, "$setOnInsert": {"created_at": now_utc()}}, upsert=True)
    notify(emp_user, "Your reporting manager assignment was updated.", "Info", "manager_assignment", employee["_id"])
    for manager_id in valid_ids:
        notify(manager_id, f"{employee.get('name')} was assigned to you as a report.", "Info", "manager_assignment", employee["_id"])
    audit(actor.get("_id"), "managers_assigned", emp_user, old, {"manager_ids": valid_ids}, employee["_id"])
    return serialize_employee(employees_collection.find_one({"_id": employee["_id"]})), None


def manager_options(user):
    perms = role_permissions(user_role(user))
    if not perms.get("is_super_user") and not perms.get("can_manage_employees"):
        return []
    if perms.get("is_super_user"):
        ensure_manager_assignments(user.get("_id"))
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
        "employee_id": employee["_id"], "employee_user_id": user.get("_id"), "manager_id": manager_for_employee(employee), "manager_ids": managers_for_employee(employee),
        "attendance_id": to_object_id(data.get("attendance_id")), "date_key": (data.get("date") or now_utc().date().isoformat())[:10],
        "requested_check_in": parse_date(data.get("requested_check_in")), "requested_check_out": parse_date(data.get("requested_check_out")),
        "reason": data.get("reason") or "Attendance correction requested", "status": "pending", "manager_note": "",
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    inserted = hrms_attendance_corrections_collection.insert_one(record).inserted_id
    if record.get("manager_ids"):
        notify_managers(record.get("manager_ids"), f"{employee.get('name')} requested attendance correction.", "Info", "attendance_correction", inserted)
    audit(user.get("_id"), "attendance_correction_requested", user.get("_id"), {}, record, inserted)
    return serialize_correction(hrms_attendance_corrections_collection.find_one({"_id": inserted})), None


def serialize_correction(row):
    employee = employees_collection.find_one({"_id": row.get("employee_id")}) if row else None
    return {"id": str(row.get("_id")), "employee_id": str(row.get("employee_id")), "employee_name": employee.get("name") if employee else "Employee", "date": row.get("date_key"), "requested_check_in": iso(row.get("requested_check_in")), "requested_check_out": iso(row.get("requested_check_out")), "reason": row.get("reason"), "status": row.get("status"), "manager_note": row.get("manager_note", "")}


def list_corrections(user):
    ids = [e["_id"] for e in employees_collection.find(team_employee_query(user), {"_id": 1})]
    return [serialize_correction(c) for c in hrms_attendance_corrections_collection.find({"employee_id": {"$in": ids}}).sort("created_at", -1).limit(100)]


def bulk_review_attendance(user, attendance_ids, action="confirm_present", note=""):
    results = []
    errors = []
    for attendance_id in attendance_ids or []:
        row, error = review_attendance(user, attendance_id, action, note)
        if error:
            errors.append({"id": str(attendance_id), "error": error})
        elif row:
            results.append(row)
    return {"updated": results, "errors": errors, "updated_count": len(results), "error_count": len(errors)}


def bulk_review_leave(user, leave_ids, action="approve", note=""):
    results = []
    errors = []
    for leave_id in leave_ids or []:
        row, error = review_leave(user, leave_id, action, note)
        if error:
            errors.append({"id": str(leave_id), "error": error})
        elif row:
            results.append(row)
    return {"updated": results, "errors": errors, "updated_count": len(results), "error_count": len(errors)}


def bulk_create_meetings(user, employee_ids, data):
    results = []
    errors = []
    for employee_id in employee_ids or []:
        payload = dict(data or {})
        payload["employee_id"] = employee_id
        row, error = create_meeting(user, payload)
        if error:
            errors.append({"employee_id": str(employee_id), "error": error})
        elif row:
            results.append(row)
    return {"meetings": results, "errors": errors, "created_count": len(results), "error_count": len(errors)}
