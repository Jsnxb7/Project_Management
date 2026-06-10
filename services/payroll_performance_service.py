from datetime import datetime, timezone
from bson import ObjectId

from database.db import (
    users_collection,
    employees_collection,
    attendance_collection,
    notifications_collection,
    hrms_audit_logs_collection,
    hrms_payroll_profiles_collection,
    hrms_payroll_cycles_collection,
    hrms_payroll_items_collection,
    hrms_payroll_adjustments_collection,
    hrms_payouts_collection,
    hrms_payroll_queries_collection,
    hrms_performance_templates_collection,
    hrms_performance_goals_collection,
)
from services.role_access import user_role, role_permissions
from services.hrms_service import to_object_id, serialize_employee, employee_manager_ids

FINANCE_ROLES = {"Super User", "Payroll Manager", "Compensation and Benefits Specialist"}
TEMPLATE_ROLES = {"Super User", "HR Director", "HR Manager", "HR Business Partner", "Learning and Development Manager", "Senior Manager"}
MANAGER_ROLES = {"Super User", "Management Admin", "HR Director", "HR Manager", "HR Business Partner", "Senior Manager"}

DEFAULT_TEMPLATES = [
    {
        "name": "Monthly Delivery Goals",
        "department": "Engineering",
        "goal_title": "Complete assigned delivery goals",
        "description": "Simple delivery goal template with checklist verification.",
        "checklist_items": ["Complete assigned tasks", "Submit testing evidence", "Update documentation"],
        "bonus_amount": 1500,
        "penalty_amount": 500,
    },
    {
        "name": "HR Operations Goals",
        "department": "HR",
        "goal_title": "Complete monthly HR operations checklist",
        "description": "Tracks HR closures, documentation, and employee query support.",
        "checklist_items": ["Close assigned HR requests", "Update employee records", "Submit monthly report"],
        "bonus_amount": 1200,
        "penalty_amount": 500,
    },
    {
        "name": "Payroll Accuracy Goals",
        "department": "Finance",
        "goal_title": "Process payroll accurately and on time",
        "description": "Tracks payroll closure, query handling, and audit readiness.",
        "checklist_items": ["Validate payroll inputs", "Resolve payroll queries", "Submit payout summary"],
        "bonus_amount": 1500,
        "penalty_amount": 750,
    },
    {
        "name": "Support Quality Goals",
        "department": "Customer Support",
        "goal_title": "Maintain support quality targets",
        "description": "Tracks ticket resolution and customer response discipline.",
        "checklist_items": ["Resolve assigned tickets", "Maintain response quality", "Update knowledge base"],
        "bonus_amount": 1000,
        "penalty_amount": 500,
    },
]


def now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.isoformat() if value and hasattr(value, "isoformat") else value


def money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def cycle_key(value=None):
    return (value or now().strftime("%Y-%m"))[:7]


def is_super(user):
    return user_role(user) == "Super User"


def is_finance(user):
    return user_role(user) in FINANCE_ROLES


def is_template_role(user):
    return user_role(user) in TEMPLATE_ROLES or is_super(user)


def current_employee(user):
    return employees_collection.find_one({"user_id": user.get("_id")}) if user else None


def is_manager_of(user, employee):
    return bool(user and employee and user.get("_id") in employee_manager_ids(employee))


def direct_reports(user):
    if not user:
        return []
    return list(employees_collection.find({
        "$or": [{"manager_id": user.get("_id")}, {"manager_ids": user.get("_id")}],
        "employment_status": {"$ne": "Inactive"},
    }).sort("name", 1).limit(500))


def performance_employees(user):
    if is_super(user):
        return list(employees_collection.find({"employment_status": {"$ne": "Inactive"}}).sort("name", 1).limit(1000))
    rows = []
    own = current_employee(user)
    if own:
        rows.append(own)
    rows.extend(direct_reports(user))
    seen = set()
    unique = []
    for row in rows:
        if row and row.get("_id") not in seen:
            seen.add(row.get("_id"))
            unique.append(row)
    return unique


def payroll_employees(user):
    if is_super(user) or is_finance(user):
        return list(employees_collection.find({"employment_status": {"$ne": "Inactive"}}).sort("name", 1).limit(1000))
    return performance_employees(user)


def can_manage_goal(user, employee):
    return bool(is_super(user) or is_manager_of(user, employee))


def can_view_employee(user, employee, payroll=False):
    if not employee:
        return False
    if payroll and (is_super(user) or is_finance(user)):
        return True
    if is_super(user):
        return True
    own = current_employee(user)
    return bool((own and own.get("_id") == employee.get("_id")) or is_manager_of(user, employee))


def can_create_payroll(user):
    return is_super(user) or is_finance(user)


def can_toggle_adjustment(user, adjustment):
    employee = employees_collection.find_one({"_id": adjustment.get("employee_id")}) if adjustment else None
    return bool(is_super(user) or is_manager_of(user, employee))


def notify(user_id, message, level="Info", category="HRMS", entity_type=None, entity_id=None):
    if not user_id:
        return
    notifications_collection.insert_one({
        "user_id": to_object_id(user_id),
        "message": message,
        "type": level,
        "category": category,
        "entity_type": entity_type or category.lower(),
        "entity_id": to_object_id(entity_id) if entity_id else None,
        "is_read": False,
        "created_at": now(),
    })


def audit(actor_id, action, target_user_id=None, old_value=None, new_value=None, record_id=None):
    hrms_audit_logs_collection.insert_one({
        "actor_id": to_object_id(actor_id),
        "action": action,
        "target_user_id": to_object_id(target_user_id) if target_user_id else None,
        "record_id": to_object_id(record_id) if record_id else None,
        "old_value": old_value or {},
        "new_value": new_value or {},
        "created_at": now(),
    })


def employee_name(employee_id):
    employee = employees_collection.find_one({"_id": employee_id}) if employee_id else None
    return employee.get("name") if employee else "Employee"


def serialize_template(row):
    return {
        "id": str(row.get("_id")) if row.get("_id") else None,
        "name": row.get("name"),
        "department": row.get("department", "General"),
        "goal_title": row.get("goal_title", row.get("name", "Performance goal")),
        "description": row.get("description", ""),
        "checklist_items": row.get("checklist_items", []),
        "bonus_amount": row.get("bonus_amount", 0),
        "penalty_amount": row.get("penalty_amount", 0),
    }


def seed_default_templates():
    if hrms_performance_templates_collection.count_documents({}) > 0:
        return
    for row in DEFAULT_TEMPLATES:
        hrms_performance_templates_collection.insert_one({**row, "is_default": True, "created_at": now(), "updated_at": now()})


def serialize_goal(row, viewer=None):
    employee = employees_collection.find_one({"_id": row.get("employee_id")}) if row else None
    checklist = row.get("checklist") or []
    total = len(checklist)
    checked = sum(1 for item in checklist if item.get("employee_checked"))
    verified = sum(1 for item in checklist if item.get("manager_verified"))
    rejected = sum(1 for item in checklist if item.get("manager_rejected"))
    score = round((verified / total) * 100, 2) if total else 0
    status = row.get("status") or ("Completed" if total and verified == total else "Needs Review" if checked else "Assigned")
    return {
        "id": str(row.get("_id")),
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "employee_name": employee.get("name") if employee else "Employee",
        "cycle_key": row.get("cycle_key"),
        "title": row.get("title"),
        "description": row.get("description", ""),
        "checklist": [{**item, "id": str(item.get("id"))} for item in checklist],
        "checked_count": checked,
        "verified_count": verified,
        "rejected_count": rejected,
        "total_count": total,
        "score": row.get("score", score),
        "status": status,
        "bonus_amount": row.get("bonus_amount", 0),
        "penalty_amount": row.get("penalty_amount", 0),
        "payroll_impact_type": row.get("payroll_impact_type", "completion_bonus"),
        "created_at": iso(row.get("created_at")),
        "updated_at": iso(row.get("updated_at")),
        "can_manage": can_manage_goal(viewer, employee) if viewer else False,
    }


def serialize_adjustment(row):
    return {
        "id": str(row.get("_id")),
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "employee_name": employee_name(row.get("employee_id")),
        "cycle_key": row.get("cycle_key"),
        "type": row.get("type"),
        "category": row.get("category"),
        "amount": row.get("amount", 0),
        "source": row.get("source", "manual"),
        "source_id": str(row.get("source_id")) if row.get("source_id") else None,
        "included": bool(row.get("included", True)),
        "manager_status": row.get("manager_status", "confirmed"),
        "reason": row.get("reason", ""),
        "created_at": iso(row.get("created_at")),
    }


def serialize_payroll_item(row):
    return {
        "id": str(row.get("_id")),
        "employee_id": str(row.get("employee_id")) if row.get("employee_id") else None,
        "employee_name": employee_name(row.get("employee_id")),
        "cycle_key": row.get("cycle_key"),
        "salary_profile_id": str(row.get("salary_profile_id")) if row.get("salary_profile_id") else None,
        "profile_base_salary": row.get("profile_base_salary", 0),
        "profile_currency": row.get("profile_currency", "INR"),
        "salary_profile_verified": bool(row.get("salary_profile_verified")),
        "salary_profile_checked_at": iso(row.get("salary_profile_checked_at")),
        "base_salary": row.get("base_salary", 0),
        "additions": row.get("additions", 0),
        "deductions": row.get("deductions", 0),
        "net_pay": row.get("net_pay", 0),
        "status": row.get("status", "draft"),
        "payout_status": row.get("payout_status", "not_paid"),
        "manual_override": bool(row.get("manual_override", False)),
        "payroll_note": row.get("payroll_note", ""),
        "created_at": iso(row.get("created_at")),
        "paid_at": iso(row.get("paid_at")),
    }


def salary_profile_for(employee):
    return hrms_payroll_profiles_collection.find_one({"employee_id": employee.get("_id")}) if employee else None


def salary_for(employee):
    profile = salary_profile_for(employee)
    if profile:
        return money(profile.get("base_salary"))
    salary = employee.get("salary") or {}
    return money(salary.get("basic") or salary.get("base_salary") or employee.get("base_salary") or 0)


def salary_snapshot(employee, fallback_salary=None):
    profile = salary_profile_for(employee)
    fallback = money(fallback_salary) if fallback_salary is not None else salary_for(employee)
    if profile:
        return {
            "salary_profile_id": profile.get("_id"),
            "profile_base_salary": money(profile.get("base_salary")),
            "profile_currency": profile.get("currency", "INR"),
            "salary_profile_verified": True,
            "salary_profile_checked_at": now(),
            "base_salary": money(profile.get("base_salary")),
        }
    return {
        "salary_profile_id": None,
        "profile_base_salary": 0,
        "profile_currency": "INR",
        "salary_profile_verified": False,
        "salary_profile_checked_at": now(),
        "base_salary": fallback,
    }


def refresh_item_salary_profile(item, recalc_base=False):
    employee = employees_collection.find_one({"_id": item.get("employee_id")}) if item else None
    if not employee:
        return item
    snapshot = salary_snapshot(employee, item.get("base_salary"))
    update = {
        "salary_profile_id": snapshot.get("salary_profile_id"),
        "profile_base_salary": snapshot.get("profile_base_salary"),
        "profile_currency": snapshot.get("profile_currency"),
        "salary_profile_verified": snapshot.get("salary_profile_verified"),
        "salary_profile_checked_at": snapshot.get("salary_profile_checked_at"),
    }
    if recalc_base and snapshot.get("salary_profile_verified") and not item.get("manual_override"):
        old_base = money(item.get("base_salary"))
        new_base = money(snapshot.get("base_salary"))
        update["base_salary"] = new_base
        update["net_pay"] = round(money(item.get("net_pay")) + (new_base - old_base), 2)
    hrms_payroll_items_collection.update_one({"_id": item.get("_id")}, {"$set": update})
    return hrms_payroll_items_collection.find_one({"_id": item.get("_id")})


def create_template(user, data):
    if not is_template_role(user):
        return None, "Only Super User, HR, or managers can create performance templates"
    items = data.get("checklist_items") or data.get("items") or []
    if isinstance(items, str):
        items = [x.strip() for x in items.split("\n") if x.strip()]
    row = {
        "name": (data.get("name") or data.get("goal_title") or "Performance Template").strip(),
        "department": data.get("department") or "General",
        "goal_title": data.get("goal_title") or data.get("name") or "Performance goal",
        "description": data.get("description") or "",
        "checklist_items": items,
        "bonus_amount": money(data.get("bonus_amount")),
        "penalty_amount": money(data.get("penalty_amount")),
        "created_by": user.get("_id"),
        "created_at": now(),
        "updated_at": now(),
    }
    inserted = hrms_performance_templates_collection.insert_one(row).inserted_id
    audit(user.get("_id"), "performance_template_created", None, {}, row, inserted)
    return serialize_template(hrms_performance_templates_collection.find_one({"_id": inserted})), None


def assign_goals(user, data):
    raw_ids = data.get("employee_ids") or []
    if not raw_ids and data.get("employee_id"):
        raw_ids = [data.get("employee_id")]
    template = hrms_performance_templates_collection.find_one({"_id": to_object_id(data.get("template_id"))}) if data.get("template_id") else None
    template = template or {}
    items = data.get("checklist_items") or data.get("items") or template.get("checklist_items") or []
    if isinstance(items, str):
        items = [x.strip() for x in items.split("\n") if x.strip()]
    title = data.get("title") or data.get("goal_title") or template.get("goal_title") or "Performance goal"
    created = []
    errors = []
    for raw_id in raw_ids:
        employee = employees_collection.find_one({"_id": to_object_id(raw_id)})
        if not employee:
            errors.append(f"Employee not found: {raw_id}")
            continue
        if not can_manage_goal(user, employee):
            errors.append(f"Not allowed for {employee.get('name')}")
            continue
        checklist = [{
            "id": str(ObjectId()),
            "title": str(item).strip(),
            "employee_checked": False,
            "manager_verified": False,
            "manager_rejected": False,
            "checked_at": None,
            "verified_at": None,
            "note": "",
        } for item in items if str(item).strip()]
        row = {
            "employee_id": employee.get("_id"),
            "user_id": employee.get("user_id"),
            "assigned_by": user.get("_id"),
            "cycle_key": cycle_key(data.get("cycle_key")),
            "title": title,
            "description": data.get("description") or template.get("description") or "",
            "checklist": checklist,
            "score": 0,
            "status": "Assigned",
            "bonus_amount": money(data.get("bonus_amount") if data.get("bonus_amount") is not None else template.get("bonus_amount")),
            "penalty_amount": money(data.get("penalty_amount") if data.get("penalty_amount") is not None else template.get("penalty_amount")),
            "payroll_impact_type": data.get("payroll_impact_type") or "completion_bonus",
            "created_at": now(),
            "updated_at": now(),
        }
        inserted = hrms_performance_goals_collection.insert_one(row).inserted_id
        notify(employee.get("user_id"), f"New performance goal assigned: {title}", "Info", "Performance", "performance_goal", inserted)
        audit(user.get("_id"), "performance_goal_assigned", employee.get("user_id"), {}, row, inserted)
        created.append(serialize_goal(hrms_performance_goals_collection.find_one({"_id": inserted}), user))
    return {"created": created, "errors": errors}, None if created else "No goals were created"


def recalc_goal(row):
    checklist = row.get("checklist") or []
    total = len(checklist)
    verified = sum(1 for item in checklist if item.get("manager_verified"))
    rejected = sum(1 for item in checklist if item.get("manager_rejected"))
    checked = sum(1 for item in checklist if item.get("employee_checked"))
    score = round((verified / total) * 100, 2) if total else 0
    if total and verified == total:
        status = "Completed"
    elif rejected:
        status = "Needs Improvement"
    elif checked:
        status = "Submitted"
    else:
        status = "Assigned"
    return score, status


def sync_goal_adjustment(goal):
    if not goal:
        return
    key = goal.get("cycle_key")
    employee = employees_collection.find_one({"_id": goal.get("employee_id")})
    if not employee:
        return
    existing = hrms_payroll_adjustments_collection.find_one({"source": "performance_goal", "source_id": goal.get("_id")})
    score = money(goal.get("score"))
    amount = 0
    adj_type = "bonus"
    category = "performance_goal_bonus"
    reason = f"Performance goal: {goal.get('title')}"
    if score >= 100 and money(goal.get("bonus_amount")):
        amount = money(goal.get("bonus_amount"))
        adj_type = "bonus"
        category = "performance_goal_bonus"
    elif goal.get("status") == "Needs Improvement" and money(goal.get("penalty_amount")):
        amount = money(goal.get("penalty_amount"))
        adj_type = "deduction"
        category = "performance_goal_penalty"
    if amount <= 0:
        if existing:
            hrms_payroll_adjustments_collection.update_one({"_id": existing.get("_id")}, {"$set": {"included": False, "amount": 0, "reason": reason, "updated_at": now()}})
        return
    row = {
        "employee_id": employee.get("_id"),
        "user_id": employee.get("user_id"),
        "cycle_key": key,
        "type": adj_type,
        "category": category,
        "amount": amount,
        "source": "performance_goal",
        "source_id": goal.get("_id"),
        "included": True,
        "manager_status": "confirmed",
        "reason": reason,
        "updated_at": now(),
    }
    if existing:
        hrms_payroll_adjustments_collection.update_one({"_id": existing.get("_id")}, {"$set": row})
    else:
        row["created_at"] = now()
        hrms_payroll_adjustments_collection.insert_one(row)


def update_checklist(user, goal_id, item_id, data, mode):
    goal = hrms_performance_goals_collection.find_one({"_id": to_object_id(goal_id)})
    if not goal:
        return None, "Goal not found"
    employee = employees_collection.find_one({"_id": goal.get("employee_id")})
    own = current_employee(user)
    if mode == "employee_check":
        if not own or own.get("_id") != goal.get("employee_id"):
            return None, "Employees can only check their own checklist items"
    else:
        if not can_manage_goal(user, employee):
            return None, "Only the assigned manager or Super User can verify this checklist"
    checklist = goal.get("checklist") or []
    found = False
    for item in checklist:
        if str(item.get("id")) != str(item_id):
            continue
        found = True
        if mode == "employee_check":
            checked = bool(data.get("checked", True))
            item.update({"employee_checked": checked, "checked_at": iso(now()) if checked else None, "employee_note": data.get("note") or item.get("employee_note", "")})
            item["manager_rejected"] = False if checked else item.get("manager_rejected", False)
        else:
            verified = data.get("verified", True)
            item.update({
                "manager_verified": bool(verified),
                "manager_rejected": not bool(verified),
                "verified_by": user.get("_id"),
                "verified_at": iso(now()),
                "note": data.get("note") or "",
            })
        break
    if not found:
        return None, "Checklist item not found"
    goal["checklist"] = checklist
    score, status = recalc_goal(goal)
    update = {"checklist": checklist, "score": score, "status": status, "updated_at": now()}
    hrms_performance_goals_collection.update_one({"_id": goal.get("_id")}, {"$set": update})
    saved = hrms_performance_goals_collection.find_one({"_id": goal.get("_id")})
    if mode != "employee_check":
        sync_goal_adjustment(saved)
        notify(employee.get("user_id"), f"Manager reviewed checklist for: {goal.get('title')}", "Info", "Performance", "performance_goal", goal.get("_id"))
    audit(user.get("_id"), f"performance_checklist_{mode}", employee.get("user_id"), serialize_goal(goal), update, goal.get("_id"))
    return serialize_goal(saved, user), None


def attendance_adjustments(employee, key):
    rows = attendance_collection.find({"employee_id": employee.get("_id"), "date_key": {"$gte": f"{key}-01", "$lte": f"{key}-31"}})
    base = salary_for(employee)
    daily = base / 22 if base else 0
    hourly = daily / 8 if daily else 0
    generated = []
    for row in rows:
        tags = set(row.get("hard_tags") or []) | {row.get("status"), row.get("manager_status")}
        if row.get("manager_status") not in ["confirmed", "approved", "excused"] and not (set(row.get("hard_tags") or []) & {"confirmed_absent", "confirmed_late", "confirmed_overtime", "half_day"}):
            continue
        reason_date = row.get("date_key") or "attendance date"
        if "confirmed_absent" in tags or row.get("status") == "absent":
            generated.append(("deduction", "attendance_absent", daily, f"Confirmed absent on {reason_date}", row.get("_id")))
        if "half_day" in tags:
            generated.append(("deduction", "attendance_half_day", daily * .5, f"Confirmed half day on {reason_date}", row.get("_id")))
        if "confirmed_overtime" in tags:
            overtime = max((row.get("worked_minutes", 0) or 0) - 480, 0)
            if overtime:
                generated.append(("bonus", "attendance_overtime", hourly * overtime / 60 * 1.25, f"Confirmed overtime on {reason_date}", row.get("_id")))
        if "confirmed_late" in tags:
            generated.append(("deduction", "attendance_late", hourly * .5, f"Confirmed late check-in on {reason_date}", row.get("_id")))
    return generated


def ensure_adjustment(employee, key, adj_type, category, amount, reason, source, source_id=None):
    amount = money(amount)
    if amount <= 0:
        return None
    query = {"employee_id": employee.get("_id"), "cycle_key": key, "category": category, "reason": reason}
    existing = hrms_payroll_adjustments_collection.find_one(query)
    row = {
        "employee_id": employee.get("_id"),
        "user_id": employee.get("user_id"),
        "cycle_key": key,
        "type": adj_type,
        "category": category,
        "amount": amount,
        "source": source,
        "source_id": source_id,
        "included": True,
        "manager_status": "confirmed",
        "reason": reason,
        "updated_at": now(),
    }
    if existing:
        hrms_payroll_adjustments_collection.update_one({"_id": existing.get("_id")}, {"$set": row})
        return existing.get("_id")
    row["created_at"] = now()
    return hrms_payroll_adjustments_collection.insert_one(row).inserted_id


def upsert_profile(user, data):
    if not can_create_payroll(user):
        return None, "Only finance users or Super User can configure payroll"
    employee = employees_collection.find_one({"_id": to_object_id(data.get("employee_id"))})
    if not employee:
        return None, "Employee is required"
    update = {
        "employee_id": employee.get("_id"),
        "user_id": employee.get("user_id"),
        "base_salary": money(data.get("base_salary")),
        "currency": data.get("currency") or "INR",
        "pay_frequency": "monthly",
        "updated_by": user.get("_id"),
        "updated_at": now(),
    }
    hrms_payroll_profiles_collection.update_one({"employee_id": employee.get("_id")}, {"$set": update, "$setOnInsert": {"created_at": now()}}, upsert=True)
    return update, None


def normalize_department_salaries(value):
    if isinstance(value, dict):
        return {str(k).strip(): money(v) for k, v in value.items() if str(k).strip() and money(v) > 0}
    if isinstance(value, list):
        result = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            department = str(item.get("department") or "").strip()
            salary = money(item.get("base_salary") or item.get("salary"))
            if department and salary > 0:
                result[department] = salary
        return result
    result = {}
    for line in str(value or "").splitlines():
        if "=" in line:
            department, salary = line.split("=", 1)
        elif ":" in line:
            department, salary = line.split(":", 1)
        else:
            continue
        department = department.strip()
        salary = money(salary.strip())
        if department and salary > 0:
            result[department] = salary
    return result


def bulk_generate_profiles(user, data):
    if not can_create_payroll(user):
        return None, "Only finance users or Super User can configure payroll"
    default_salary = money(data.get("default_base_salary") or data.get("base_salary"))
    department_salaries = normalize_department_salaries(data.get("department_salaries"))
    target_department = (data.get("department") or "").strip()
    if default_salary <= 0 and not department_salaries:
        return None, "Provide a default salary or department salary map"
    query = {"employment_status": {"$ne": "Inactive"}}
    if target_department:
        query["department"] = target_department
    employees = list(employees_collection.find(query).sort("department", 1).limit(2000))
    updated = []
    skipped = []
    for employee in employees:
        salary = department_salaries.get(employee.get("department")) or default_salary
        if salary <= 0:
            skipped.append(employee.get("name") or str(employee.get("_id")))
            continue
        row, error = upsert_profile(user, {
            "employee_id": str(employee.get("_id")),
            "base_salary": salary,
            "currency": data.get("currency") or "INR",
        })
        if error:
            skipped.append(employee.get("name") or str(employee.get("_id")))
        else:
            updated.append(row)
    audit(user.get("_id"), "salary_profiles_generated", None, {}, {"updated": len(updated), "skipped": len(skipped)})
    return {"updated": updated, "skipped": skipped}, None


def generate_payroll(user, data):
    if not can_create_payroll(user):
        return None, "Only finance users or Super User can create payrolls"
    key = cycle_key(data.get("cycle_key"))
    employee_ids = [to_object_id(x) for x in (data.get("employee_ids") or []) if to_object_id(x)]
    if data.get("employee_id"):
        emp_id = to_object_id(data.get("employee_id"))
        if emp_id and emp_id not in employee_ids:
            employee_ids.append(emp_id)
    department = (data.get("department") or "").strip()
    query = {"employment_status": {"$ne": "Inactive"}}
    if employee_ids:
        query["_id"] = {"$in": employee_ids}
    elif department:
        query["department"] = department
    employees = list(employees_collection.find(query).sort("name", 1).limit(1000))
    created = []
    for employee in employees:
        existing_item = hrms_payroll_items_collection.find_one({"employee_id": employee.get("_id"), "cycle_key": key})
        if existing_item and existing_item.get("payout_status") == "paid" and not data.get("force_regenerate"):
            created.append(serialize_payroll_item(existing_item))
            continue
        base_override = data.get("base_salary_override")
        if base_override:
            base = money(base_override)
            upsert_profile(user, {"employee_id": str(employee.get("_id")), "base_salary": base, "currency": data.get("currency") or "INR"})
        snapshot = salary_snapshot(employee, base_override)
        base = snapshot["base_salary"]
        for adj_type, category, amount, reason, source_id in attendance_adjustments(employee, key):
            ensure_adjustment(employee, key, adj_type, category, amount, reason, "attendance", source_id)
        adjustments = list(hrms_payroll_adjustments_collection.find({"employee_id": employee.get("_id"), "cycle_key": key}))
        included = [a for a in adjustments if a.get("included", True)]
        additions = sum(money(a.get("amount")) for a in included if a.get("type") in ["bonus", "addition", "overtime", "direct_bonus"])
        deductions = sum(money(a.get("amount")) for a in included if a.get("type") in ["deduction", "penalty"])
        net = round(base + additions - deductions, 2)
        item = {
            "employee_id": employee.get("_id"),
            "user_id": employee.get("user_id"),
            "cycle_key": key,
            "salary_profile_id": snapshot.get("salary_profile_id"),
            "profile_base_salary": snapshot.get("profile_base_salary"),
            "profile_currency": snapshot.get("profile_currency"),
            "salary_profile_verified": snapshot.get("salary_profile_verified"),
            "salary_profile_checked_at": snapshot.get("salary_profile_checked_at"),
            "base_salary": base,
            "additions": additions,
            "deductions": deductions,
            "net_pay": net,
            "status": "ready_for_manager_review",
            "payout_status": "not_paid",
            "manual_override": False,
            "created_by": user.get("_id"),
            "updated_at": now(),
        }
        hrms_payroll_items_collection.update_one({"employee_id": employee.get("_id"), "cycle_key": key}, {"$set": item, "$setOnInsert": {"created_at": now()}}, upsert=True)
        saved = hrms_payroll_items_collection.find_one({"employee_id": employee.get("_id"), "cycle_key": key})
        created.append(serialize_payroll_item(saved))
        for mid in employee_manager_ids(employee):
            notify(mid, f"Payroll review is ready for {employee.get('name')} ({key}).", "Warning", "Payroll", "payroll_item", saved.get("_id"))
    cycle = {"cycle_key": key, "status": "generated", "updated_at": now(), "created_by": user.get("_id")}
    hrms_payroll_cycles_collection.update_one({"cycle_key": key}, {"$set": cycle, "$setOnInsert": {"created_at": now()}}, upsert=True)
    audit(user.get("_id"), "simple_payroll_generated", None, {}, {"cycle_key": key, "count": len(created)})
    return {"items": created}, None


def toggle_adjustment(user, adjustment_id, included=True):
    adjustment = hrms_payroll_adjustments_collection.find_one({"_id": to_object_id(adjustment_id)})
    if not adjustment:
        return None, "Adjustment not found"
    if not can_toggle_adjustment(user, adjustment):
        return None, "Only the assigned manager or Super User can include/exclude this payroll adjustment"
    update = {"included": bool(included), "toggled_by": user.get("_id"), "updated_at": now()}
    hrms_payroll_adjustments_collection.update_one({"_id": adjustment.get("_id")}, {"$set": update})
    generate_payroll({**user, "hrms_role": "Super User"}, {"employee_id": str(adjustment.get("employee_id")), "cycle_key": adjustment.get("cycle_key")})
    saved = hrms_payroll_adjustments_collection.find_one({"_id": adjustment.get("_id")})
    audit(user.get("_id"), "payroll_adjustment_toggled", adjustment.get("user_id"), serialize_adjustment(adjustment), update, adjustment.get("_id"))
    return serialize_adjustment(saved), None


def confirm_payroll(user, item_id, action="confirm"):
    item = hrms_payroll_items_collection.find_one({"_id": to_object_id(item_id)})
    if not item:
        return None, "Payroll item not found"
    item = refresh_item_salary_profile(item, recalc_base=True)
    employee = employees_collection.find_one({"_id": item.get("employee_id")})
    if not (is_super(user) or is_manager_of(user, employee)):
        return None, "Only the assigned manager or Super User can confirm this payroll"
    status = "manager_confirmed" if action == "confirm" else "needs_changes"
    update = {"status": status, "confirmed_by": user.get("_id"), "confirmed_at": now(), "updated_at": now()}
    hrms_payroll_items_collection.update_one({"_id": item.get("_id")}, {"$set": update})
    return serialize_payroll_item(hrms_payroll_items_collection.find_one({"_id": item.get("_id")})), None


def edit_payroll_item(user, item_id, data):
    if not can_create_payroll(user):
        return None, "Only finance users or Super User can edit payroll"
    item = hrms_payroll_items_collection.find_one({"_id": to_object_id(item_id)})
    if not item:
        return None, "Payroll item not found"
    if item.get("payout_status") == "paid" and not data.get("allow_paid_edit"):
        return None, "Paid payroll cannot be edited unless paid edit is explicitly allowed"
    employee = employees_collection.find_one({"_id": item.get("employee_id")})
    if not employee:
        return None, "Employee not found"
    base = money(data.get("base_salary") if data.get("base_salary") is not None else item.get("base_salary"))
    additions = money(data.get("additions") if data.get("additions") is not None else item.get("additions"))
    deductions = money(data.get("deductions") if data.get("deductions") is not None else item.get("deductions"))
    net = money(data.get("net_pay")) if data.get("net_pay") not in [None, ""] else round(base + additions - deductions, 2)
    if data.get("update_salary_profile"):
        upsert_profile(user, {"employee_id": str(employee.get("_id")), "base_salary": base, "currency": data.get("currency") or item.get("profile_currency") or "INR"})
    snapshot = salary_snapshot(employee, base)
    update = {
        "salary_profile_id": snapshot.get("salary_profile_id"),
        "profile_base_salary": snapshot.get("profile_base_salary"),
        "profile_currency": snapshot.get("profile_currency"),
        "salary_profile_verified": snapshot.get("salary_profile_verified"),
        "salary_profile_checked_at": snapshot.get("salary_profile_checked_at"),
        "base_salary": base,
        "additions": additions,
        "deductions": deductions,
        "net_pay": net,
        "manual_override": True,
        "payroll_note": data.get("payroll_note") or data.get("reason") or item.get("payroll_note", ""),
        "status": data.get("status") or "ready_for_manager_review",
        "edited_by": user.get("_id"),
        "edited_at": now(),
        "updated_at": now(),
    }
    hrms_payroll_items_collection.update_one({"_id": item.get("_id")}, {"$set": update})
    saved = hrms_payroll_items_collection.find_one({"_id": item.get("_id")})
    audit(user.get("_id"), "payroll_item_edited", item.get("user_id"), serialize_payroll_item(item), update, item.get("_id"))
    return serialize_payroll_item(saved), None


def payout_payroll(user, item_id):
    if not can_create_payroll(user):
        return None, "Only finance users or Super User can mark payouts"
    item = hrms_payroll_items_collection.find_one({"_id": to_object_id(item_id)})
    if not item:
        return None, "Payroll item not found"
    item = refresh_item_salary_profile(item, recalc_base=True)
    if item.get("status") != "manager_confirmed" and not is_super(user):
        return None, "Manager confirmation is required before payout"
    update = {"payout_status": "paid", "status": "paid", "paid_by": user.get("_id"), "paid_at": now(), "updated_at": now()}
    hrms_payroll_items_collection.update_one({"_id": item.get("_id")}, {"$set": update})
    hrms_payouts_collection.insert_one({"employee_id": item.get("employee_id"), "user_id": item.get("user_id"), "cycle_key": item.get("cycle_key"), "amount": item.get("net_pay"), "status": "paid", "paid_by": user.get("_id"), "paid_at": now(), "created_at": now()})
    notify(item.get("user_id"), f"Payroll paid for {item.get('cycle_key')}: ₹{item.get('net_pay')}", "Success", "Payroll", "payroll_item", item.get("_id"))
    return serialize_payroll_item(hrms_payroll_items_collection.find_one({"_id": item.get("_id")})), None


def custom_payroll_payout(user, data):
    if not can_create_payroll(user):
        return None, "Only finance users or Super User can make custom payouts"
    employee = employees_collection.find_one({"_id": to_object_id(data.get("employee_id"))})
    if not employee:
        return None, "Employee is required"
    amount = money(data.get("amount") or data.get("net_pay"))
    if amount <= 0:
        return None, "Custom pay amount must be greater than zero"
    key = cycle_key(data.get("cycle_key"))
    snapshot = salary_snapshot(employee, data.get("base_salary"))
    item = {
        "employee_id": employee.get("_id"),
        "user_id": employee.get("user_id"),
        "cycle_key": key,
        "salary_profile_id": snapshot.get("salary_profile_id"),
        "profile_base_salary": snapshot.get("profile_base_salary"),
        "profile_currency": snapshot.get("profile_currency"),
        "salary_profile_verified": snapshot.get("salary_profile_verified"),
        "salary_profile_checked_at": snapshot.get("salary_profile_checked_at"),
        "base_salary": snapshot.get("base_salary"),
        "additions": money(data.get("additions")),
        "deductions": money(data.get("deductions")),
        "net_pay": amount,
        "status": "paid",
        "payout_status": "paid",
        "manual_override": True,
        "custom_pay": True,
        "payroll_note": data.get("reason") or "Custom pay now",
        "paid_by": user.get("_id"),
        "paid_at": now(),
        "updated_at": now(),
    }
    existing = hrms_payroll_items_collection.find_one({"employee_id": employee.get("_id"), "cycle_key": key, "custom_pay": True, "payroll_note": item["payroll_note"]})
    if existing:
        hrms_payroll_items_collection.update_one({"_id": existing.get("_id")}, {"$set": item})
        item_id = existing.get("_id")
    else:
        item["created_by"] = user.get("_id")
        item["created_at"] = now()
        item_id = hrms_payroll_items_collection.insert_one(item).inserted_id
    hrms_payouts_collection.insert_one({"employee_id": employee.get("_id"), "user_id": employee.get("user_id"), "cycle_key": key, "amount": amount, "status": "paid", "kind": "custom_pay", "reason": item["payroll_note"], "paid_by": user.get("_id"), "paid_at": now(), "created_at": now()})
    notify(employee.get("user_id"), f"Custom payroll paid for {key}: {amount}", "Success", "Payroll", "payroll_item", item_id)
    audit(user.get("_id"), "custom_payroll_paid", employee.get("user_id"), {}, item, item_id)
    return serialize_payroll_item(hrms_payroll_items_collection.find_one({"_id": item_id})), None


def payroll_workspace(user, summary_only=False):
    employees = payroll_employees(user)
    ids = [e.get("_id") for e in employees if e]
    q = {"employee_id": {"$in": ids}} if ids else {"employee_id": None}
    if summary_only:
        return {
            "role": user_role(user),
            "permissions": {
                "is_super": is_super(user),
                "is_finance": is_finance(user),
                "can_create_payroll": can_create_payroll(user),
                "can_confirm_payroll": is_super(user) or bool(direct_reports(user)),
            },
            "employees": [],
            "items": [],
            "adjustments": [],
            "profiles": [],
            "summary": {
                "items": hrms_payroll_items_collection.count_documents(q),
                "pending_manager": hrms_payroll_items_collection.count_documents({**q, "status": "ready_for_manager_review"}),
                "paid": hrms_payroll_items_collection.count_documents({**q, "payout_status": "paid"}),
                "adjustments": hrms_payroll_adjustments_collection.count_documents(q),
            },
        }
    items = [serialize_payroll_item(r) for r in hrms_payroll_items_collection.find(q).sort("cycle_key", -1).limit(300)]
    adjustments = [serialize_adjustment(r) for r in hrms_payroll_adjustments_collection.find(q).sort("created_at", -1).limit(500)]
    profiles = [{"id": str(p.get("_id")), "employee_id": str(p.get("employee_id")), "employee_name": employee_name(p.get("employee_id")), "base_salary": p.get("base_salary", 0), "currency": p.get("currency", "INR")} for p in hrms_payroll_profiles_collection.find(q).sort("updated_at", -1).limit(300)]
    return {
        "role": user_role(user),
        "permissions": {
            "is_super": is_super(user),
            "is_finance": is_finance(user),
            "can_create_payroll": can_create_payroll(user),
            "can_confirm_payroll": is_super(user) or bool(direct_reports(user)),
        },
        "employees": [serialize_employee(e) for e in employees],
        "items": items,
        "adjustments": adjustments,
        "profiles": profiles,
        "summary": {
            "items": len(items),
            "pending_manager": len([i for i in items if i.get("status") == "ready_for_manager_review"]),
            "paid": len([i for i in items if i.get("payout_status") == "paid"]),
            "adjustments": len(adjustments),
        },
    }


def performance_workspace(user, summary_only=False):
    seed_default_templates()
    employees = performance_employees(user)
    ids = [e.get("_id") for e in employees if e]
    q = {"employee_id": {"$in": ids}} if ids else {"employee_id": None}
    if summary_only:
        return {
            "role": user_role(user),
            "permissions": {
                "is_super": is_super(user),
                "can_create_templates": is_template_role(user),
                "can_assign_goals": is_super(user) or bool(direct_reports(user)),
            },
            "employees": [],
            "templates": [],
            "goals": [],
            "summary": {
                "goals": hrms_performance_goals_collection.count_documents(q),
                "submitted": hrms_performance_goals_collection.count_documents({**q, "status": "Submitted"}),
                "completed": hrms_performance_goals_collection.count_documents({**q, "status": "Completed"}),
                "needs_improvement": hrms_performance_goals_collection.count_documents({**q, "status": "Needs Improvement"}),
            },
        }
    goals = [serialize_goal(g, user) for g in hrms_performance_goals_collection.find(q).sort("created_at", -1).limit(500)]
    templates = [serialize_template(t) for t in hrms_performance_templates_collection.find({}).sort("name", 1).limit(200)]
    return {
        "role": user_role(user),
        "permissions": {
            "is_super": is_super(user),
            "can_create_templates": is_template_role(user),
            "can_assign_goals": is_super(user) or bool(direct_reports(user)),
        },
        "employees": [serialize_employee(e) for e in employees],
        "templates": templates,
        "goals": goals,
        "summary": {
            "goals": len(goals),
            "submitted": len([g for g in goals if g.get("status") == "Submitted"]),
            "completed": len([g for g in goals if g.get("status") == "Completed"]),
            "needs_improvement": len([g for g in goals if g.get("status") == "Needs Improvement"]),
        },
    }
