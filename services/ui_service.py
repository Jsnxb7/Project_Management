from services.page_access import can_access_page
from services.role_access import normalize_role, role_permissions

UI_NAV_GROUPS = [
    {
        "key": "overview",
        "label": "Overview",
        "items": [{"key": "dashboard", "label": "Dashboard", "path": "/dashboard", "icon": "▣"}],
    },
    {
        "key": "people",
        "label": "People",
        "items": [
            {"key": "employees", "label": "Employees", "path": "/employees", "icon": "◉"},
            {"key": "attendance", "label": "Attendance", "path": "/attendance", "icon": "◷"},
            {"key": "performance", "label": "Performance", "path": "/performance", "icon": "◇"},
            {"key": "payroll", "label": "Payroll", "path": "/payroll", "icon": "₹"},
        ],
    },
    {
        "key": "recruitment",
        "label": "Recruitment",
        "items": [
            {"key": "recruitment", "label": "Recruitment", "path": "/recruitment", "icon": "✧"},
            {"key": "applications", "label": "Applications", "path": "/applications", "icon": "▤"},
            {"key": "interviews", "label": "Interview Rooms", "path": "/interviews", "icon": "◌"},
            {"key": "voice_interview", "label": "Voice AI Lab", "path": "/voice-interview", "icon": "♬"},
        ],
    },
    {
        "key": "candidate",
        "label": "Candidate",
        "items": [{"key": "candidate_process", "label": "My Interview Steps", "path": "/candidate-process", "icon": "◈"}],
    },
    {
        "key": "self_service",
        "label": "Self-Service",
        "items": [
            {"key": "messages", "label": "Messages", "path": "/messages", "icon": "✉"},
            {"key": "notifications", "label": "Notifications", "path": "/notifications", "icon": "!"},
            {"key": "profile", "label": "Profile", "path": "/profile", "icon": "●"},
            {"key": "themes", "label": "Theme Kits", "path": "/themes", "icon": "◐"},
        ],
    },
    {
        "key": "admin",
        "label": "Admin",
        "items": [
            {"key": "users", "label": "Users", "path": "/portal/users", "icon": "▥"},
            {"key": "bulk_import", "label": "Bulk Import", "path": "/portal/import-users", "icon": "⇪"},
        ],
    },
]

PAGE_UI_RULES = {
    "attendance": {
        "employee_tabs": ["My Day", "Calendar", "Leave", "Corrections"],
        "manager_tabs": ["Team", "Leave Approvals", "Anomalies", "Meetings"],
        "super_tabs": ["Rules", "Overrides", "Reports"],
    },
    "payroll": {
        "employee_tabs": ["My Payroll", "Payslips", "Queries"],
        "manager_tabs": ["Team Confirmations", "Adjustments"],
        "finance_tabs": ["Configure", "Cycles", "Bonuses", "Deductions", "Payouts"],
        "super_tabs": ["Rules", "Audit", "Overrides"],
    },
    "performance": {
        "employee_tabs": ["My Goals", "Scores", "Feedback"],
        "manager_tabs": ["Team Reviews", "Milestones", "Payroll Impact"],
        "hr_tabs": ["Cycles", "Goal Templates", "Reports"],
        "super_tabs": ["Rules", "Overrides"],
    },
}


def visible_nav_for_role(role):
    role = normalize_role(role)
    groups = []
    for group in UI_NAV_GROUPS:
        items = [item for item in group["items"] if can_access_page(role, item["path"])]
        if items:
            groups.append({**group, "items": items})
    return groups


def ui_shell_for_role(role):
    role = normalize_role(role)
    return {
        "role": role,
        "permissions": role_permissions(role),
        "nav_groups": visible_nav_for_role(role),
        "page_ui_rules": PAGE_UI_RULES,
    }
