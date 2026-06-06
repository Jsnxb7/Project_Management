from datetime import datetime, timezone
from collections import Counter, defaultdict

from database.db import (
    users_collection,
    employees_collection,
    attendance_collection,
    leave_requests_collection,
    notifications_collection,
    activity_logs_collection,
    applications_collection,
    jobs_collection,
    resume_screening_collection,
    interview_rooms_collection,
    hrms_payroll_items_collection,
    hrms_payroll_adjustments_collection,
    hrms_payroll_profiles_collection,
    hrms_payouts_collection,
    hrms_performance_goals_collection,
    hrms_performance_templates_collection,
    hrms_manager_assignments_collection,
    hrms_audit_logs_collection,
)
from services.hrms_service import (
    current_employee_for_user,
    serialize_employee,
    scoped_employee_query,
    assigned_employee_query,
    employee_manager_ids,
    to_object_id,
)
from services.role_access import user_role, role_permissions


def _iso(value):
    return value.isoformat() if value and hasattr(value, "isoformat") else value


def _money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def _pct(part, whole):
    return round((part / whole) * 100, 1) if whole else 0


def _count(collection, query=None):
    return collection.count_documents(query or {})


def _employees_for_user(user, *, company=False, assigned=False):
    perms = role_permissions(user_role(user))
    if company and (perms.get("is_super_user") or perms.get("can_view_company_dashboard") or perms.get("is_finance")):
        query = {"employment_status": {"$ne": "Inactive"}}
    elif assigned:
        query = assigned_employee_query(user)
    else:
        query = scoped_employee_query(user)
    return list(employees_collection.find(query).sort("name", 1).limit(2000))


def _employee_ids(rows):
    return [row.get("_id") for row in rows if row and row.get("_id")]


def _today_key():
    return datetime.now(timezone.utc).date().isoformat()


def attendance_summary(employee_ids):
    if not employee_ids:
        return {
            "present_today": 0,
            "checked_in_today": 0,
            "absent_today": 0,
            "late_today": 0,
            "overtime_today": 0,
            "on_leave_today": 0,
            "pending_anomalies": 0,
            "pending_leaves": 0,
            "total_logs": 0,
            "ring": {"value": 0, "label": "Attendance"},
        }
    base = {"employee_id": {"$in": employee_ids}}
    today = {**base, "date_key": _today_key()}
    present = _count(attendance_collection, {**today, "status": {"$in": ["present", "checked_in", "Present", "Checked In"]}})
    total_people = len(employee_ids)
    return {
        "present_today": present,
        "checked_in_today": _count(attendance_collection, {**today, "check_in": {"$exists": True}}),
        "absent_today": _count(attendance_collection, {**today, "status": {"$in": ["absent", "Absent"]}}),
        "late_today": _count(attendance_collection, {**today, "$or": [{"soft_tags": "late_checkin"}, {"hard_tags": "confirmed_late"}, {"late_mark": True}]}),
        "overtime_today": _count(attendance_collection, {**today, "$or": [{"soft_tags": "overtime"}, {"hard_tags": "confirmed_overtime"}]}),
        "on_leave_today": _count(attendance_collection, {**today, "status": {"$in": ["leave", "Leave Approved", "approved_leave"]}}),
        "pending_anomalies": _count(attendance_collection, {**base, "manager_status": {"$in": ["pending_review", "review_required"]}}),
        "pending_leaves": _count(leave_requests_collection, {**base, "status": {"$in": ["Pending", "pending"]}}),
        "total_logs": _count(attendance_collection, base),
        "ring": {"value": _pct(present, total_people), "label": "Present today"},
    }


def payroll_summary(employee_ids):
    if not employee_ids:
        return {
            "items": 0,
            "pending_manager": 0,
            "payout_ready": 0,
            "paid": 0,
            "blocked": 0,
            "additions": 0,
            "deductions": 0,
            "net_pay": 0,
        }
    base = {"employee_id": {"$in": employee_ids}}
    items = list(hrms_payroll_items_collection.find(base).sort("cycle_key", -1).limit(1000))
    adjustments = list(hrms_payroll_adjustments_collection.find(base).sort("created_at", -1).limit(1000))
    return {
        "items": len(items),
        "pending_manager": len([i for i in items if i.get("status") in ["ready_for_manager_review", "manager_pending"]]),
        "payout_ready": len([i for i in items if i.get("status") == "manager_confirmed" and i.get("payout_status") != "paid"]),
        "paid": len([i for i in items if i.get("payout_status") == "paid" or i.get("status") == "paid"]),
        "blocked": len([i for i in items if i.get("status") in ["blocked", "needs_changes"]]),
        "additions": _money(sum(_money(a.get("amount")) for a in adjustments if a.get("included", True) and a.get("type") in ["bonus", "addition", "overtime", "direct_bonus"])),
        "deductions": _money(sum(_money(a.get("amount")) for a in adjustments if a.get("included", True) and a.get("type") in ["deduction", "penalty"])),
        "net_pay": _money(sum(_money(i.get("net_pay")) for i in items)),
    }


def performance_summary(employee_ids):
    if not employee_ids:
        return {
            "goals": 0,
            "assigned": 0,
            "submitted": 0,
            "completed": 0,
            "needs_improvement": 0,
            "pending_verification": 0,
            "average_score": 0,
        }
    base = {"employee_id": {"$in": employee_ids}}
    goals = list(hrms_performance_goals_collection.find(base).sort("created_at", -1).limit(1000))
    scores = [_money(g.get("score")) for g in goals if g.get("score") is not None]
    pending = 0
    for goal in goals:
        for item in goal.get("checklist") or []:
            if item.get("employee_checked") and not item.get("manager_verified") and not item.get("manager_rejected"):
                pending += 1
    return {
        "goals": len(goals),
        "assigned": len([g for g in goals if g.get("status") == "Assigned"]),
        "submitted": len([g for g in goals if g.get("status") == "Submitted"]),
        "completed": len([g for g in goals if g.get("status") == "Completed"]),
        "needs_improvement": len([g for g in goals if g.get("status") == "Needs Improvement"]),
        "pending_verification": pending,
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
    }


def people_summary(rows):
    departments = Counter(row.get("department") or "Unassigned" for row in rows)
    managers_missing = 0
    for row in rows:
        if not employee_manager_ids(row) and row.get("employment_status") != "Inactive":
            managers_missing += 1
    return {
        "total": len(rows),
        "active": len([r for r in rows if r.get("employment_status", "Active") == "Active"]),
        "inactive": len([r for r in rows if r.get("employment_status") == "Inactive"]),
        "manager_missing": managers_missing,
        "departments": [{"name": name, "count": count} for name, count in departments.most_common(8)],
    }


def recruitment_summary():
    by_status = list(applications_collection.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]))
    return {
        "open_jobs": _count(jobs_collection, {"status": "Open"}),
        "applications": _count(applications_collection, {}),
        "shortlisted": _count(applications_collection, {"status": "Shortlisted"}),
        "rejected": _count(applications_collection, {"status": "Rejected"}),
        "ai_reports_ready": _count(resume_screening_collection, {}),
        "interview_rooms": _count(interview_rooms_collection, {}),
        "pipeline": [{"status": row.get("_id") or "New", "count": row.get("count", 0)} for row in by_status],
    }


def notifications_summary(user):
    return {
        "unread": _count(notifications_collection, {"user_id": user.get("_id"), "is_read": False}),
        "recent": [
            {
                "message": n.get("message"),
                "type": n.get("type") or n.get("level") or "Info",
                "created_at": _iso(n.get("created_at")),
            }
            for n in notifications_collection.find({"user_id": user.get("_id")}).sort("created_at", -1).limit(5)
        ],
    }


def pending_actions(user, own_ids, team_ids, company_ids, perms):
    actions = []
    if team_ids or perms.get("is_super_user"):
        review_ids = company_ids if perms.get("is_super_user") else team_ids
        actions.append({"label": "Attendance anomalies", "count": attendance_summary(review_ids).get("pending_anomalies", 0), "href": "/attendance", "tone": "warning"})
        actions.append({"label": "Leave approvals", "count": attendance_summary(review_ids).get("pending_leaves", 0), "href": "/attendance", "tone": "info"})
        actions.append({"label": "Checklist verifications", "count": performance_summary(review_ids).get("pending_verification", 0), "href": "/performance", "tone": "warning"})
        actions.append({"label": "Payroll confirmations", "count": payroll_summary(review_ids).get("pending_manager", 0), "href": "/payroll", "tone": "danger"})
    if perms.get("is_finance") or perms.get("is_super_user"):
        actions.append({"label": "Payout-ready payrolls", "count": payroll_summary(company_ids).get("payout_ready", 0), "href": "/payroll", "tone": "success"})
    actions.append({"label": "Unread notifications", "count": notifications_summary(user).get("unread", 0), "href": "/notifications", "tone": "info"})
    return [a for a in actions if a.get("count", 0) > 0][:8]


def recent_activity(employee_ids):
    items = []
    if employee_ids:
        base = {"employee_id": {"$in": employee_ids}}
        for row in attendance_collection.find(base).sort("updated_at", -1).limit(4):
            items.append({"kind": "Attendance", "label": row.get("status") or row.get("date_key") or "Attendance updated", "created_at": _iso(row.get("updated_at") or row.get("created_at"))})
        for row in hrms_performance_goals_collection.find(base).sort("updated_at", -1).limit(4):
            items.append({"kind": "Performance", "label": row.get("title") or "Goal updated", "created_at": _iso(row.get("updated_at") or row.get("created_at"))})
        for row in hrms_payroll_items_collection.find(base).sort("updated_at", -1).limit(4):
            items.append({"kind": "Payroll", "label": f"{row.get('cycle_key', 'Cycle')} · {row.get('status', 'Draft')}", "created_at": _iso(row.get("updated_at") or row.get("created_at"))})
    return sorted(items, key=lambda x: x.get("created_at") or "", reverse=True)[:8]


def system_health():
    missing_manager = employees_collection.count_documents({"employment_status": {"$ne": "Inactive"}, "$or": [{"manager_id": None}, {"manager_status": "missing"}]})
    return {
        "json_mongo_mode": "two_way_mirror_registry",
        "missing_manager_assignments": missing_manager,
        "audit_logs": hrms_audit_logs_collection.count_documents({}),
        "ui_registry": "clean",
    }


def dashboard_summary_for(user):
    role = user_role(user)
    perms = role_permissions(role)
    own_employee = current_employee_for_user(user.get("_id"))
    own_ids = [own_employee.get("_id")] if own_employee else []
    scoped_rows = _employees_for_user(user)
    scoped_ids = _employee_ids(scoped_rows)
    team_rows = _employees_for_user(user, assigned=True)
    team_ids = _employee_ids(team_rows)
    company_rows = _employees_for_user(user, company=True)
    company_ids = _employee_ids(company_rows)

    primary_ids = company_ids if perms.get("can_view_company_dashboard") or perms.get("is_finance") else team_ids if team_ids else own_ids or scoped_ids

    summary = {
        "role": role,
        "permissions": perms,
        "scope": {
            "kind": "company" if primary_ids == company_ids and company_ids else "team" if team_ids else "self",
            "visible_employee_count": len(primary_ids),
            "own_employee": serialize_employee(own_employee),
        },
        "people": people_summary(company_rows if perms.get("can_view_company_dashboard") else scoped_rows),
        "attendance": attendance_summary(primary_ids),
        "performance": performance_summary(primary_ids),
        "payroll": payroll_summary(company_ids if perms.get("is_finance") or perms.get("is_super_user") else primary_ids),
        "notifications": notifications_summary(user),
        "pending_actions": pending_actions(user, own_ids, team_ids, company_ids, perms),
        "recent_activity": recent_activity(primary_ids),
        "widgets": [],
    }

    if perms.get("can_view_recruitment"):
        summary["recruitment"] = recruitment_summary()
    if perms.get("is_super_user"):
        summary["system_health"] = system_health()
    if team_ids:
        summary["team"] = people_summary(team_rows)
    if own_ids:
        summary["self"] = {
            "attendance": attendance_summary(own_ids),
            "performance": performance_summary(own_ids),
            "payroll": payroll_summary(own_ids),
        }
    summary["widgets"] = build_widgets(summary)
    return summary


def build_widgets(summary):
    widgets = []
    people = summary.get("people", {})
    attendance = summary.get("attendance", {})
    performance = summary.get("performance", {})
    payroll = summary.get("payroll", {})
    widgets.extend([
        {"key": "people", "label": "Visible Employees", "value": people.get("total", 0), "subtext": f"{people.get('active', 0)} active", "href": "/employees", "tone": "info"},
        {"key": "attendance", "label": "Present Today", "value": attendance.get("present_today", 0), "subtext": f"{attendance.get('late_today', 0)} late · {attendance.get('absent_today', 0)} absent", "href": "/attendance", "tone": "success"},
        {"key": "performance", "label": "Performance Score", "value": f"{performance.get('average_score', 0)}%", "subtext": f"{performance.get('pending_verification', 0)} checks pending", "href": "/performance", "tone": "warning"},
        {"key": "payroll", "label": "Payroll Pending", "value": payroll.get("pending_manager", 0), "subtext": f"₹{payroll.get('net_pay', 0)} net visible", "href": "/payroll", "tone": "danger"},
    ])
    if summary.get("recruitment"):
        rec = summary["recruitment"]
        widgets.append({"key": "recruitment", "label": "Open Jobs", "value": rec.get("open_jobs", 0), "subtext": f"{rec.get('applications', 0)} applications", "href": "/recruitment", "tone": "info"})
    if summary.get("system_health"):
        sys = summary["system_health"]
        widgets.append({"key": "system", "label": "System Health", "value": sys.get("missing_manager_assignments", 0), "subtext": "missing manager assignments", "href": "/employees", "tone": "warning"})
    return widgets
