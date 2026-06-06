from services.role_access import normalize_role, role_permissions


PAGE_ACCESS = {
    "/dashboard": lambda perms: perms.get("can_view_self_service"),
    "/employees": lambda perms: perms.get("can_view_employees"),
    "/attendance": lambda perms: perms.get("can_view_self_service"),
    "/payroll": lambda perms: perms.get("can_view_payroll"),
    "/performance": lambda perms: perms.get("can_view_performance"),
    "/recruitment": lambda perms: perms.get("can_view_recruitment"),
    "/applications": lambda perms: perms.get("can_view_recruitment"),
    "/second-round-candidates": lambda perms: perms.get("can_view_recruitment"),
    "/voice-interview": lambda perms: perms.get("can_run_voice_interviews"),
    "/interviews": lambda perms: perms.get("can_run_voice_interviews"),
    "/candidate-process": lambda perms: perms.get("can_view_candidate_process") or perms.get("is_super_user"),
    "/themes": lambda perms: perms.get("can_customize_theme") and perms.get("can_view_self_service"),
    "/notifications": lambda perms: perms.get("can_view_self_service"),
    "/messages": lambda perms: perms.get("can_message_employees"),
    "/profile": lambda perms: perms.get("can_view_self_service"),
    "/portal/users": lambda perms: perms.get("can_manage_users"),
    "/portal/import-users": lambda perms: perms.get("is_super_user"),
}


def can_access_page(role, path):
    role = normalize_role(role)
    perms = role_permissions(role)
    matcher = PAGE_ACCESS.get(path)
    return bool(matcher and matcher(perms))


def default_page_for_role(role):
    role = normalize_role(role)
    if can_access_page(role, "/dashboard"):
        return "dashboard_page"
    if can_access_page(role, "/candidate-process"):
        return "candidate_process_page"
    return "index"
