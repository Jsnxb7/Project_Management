HRMS_ROLES = [
    "Super User",
    "Management Admin",
    "HR Director",
    "HR Manager",
    "HR Business Partner",
    "HR Recruiter",
    "Talent Acquisition Specialist",
    "Technical Interviewer",
    "Panel Interviewer",
    "Payroll Manager",
    "Compensation and Benefits Specialist",
    "Learning and Development Manager",
    "Employee Relations Manager",
    "HR Operations Specialist",
    "Senior Manager",
    "Employee",
    "Candidate",
]

HR_POSITION_FAMILIES = {
    "HR Leadership": ["HR Director", "HR Manager", "HR Business Partner"],
    "Talent Acquisition": ["HR Recruiter", "Talent Acquisition Specialist"],
    "Payroll and Rewards": ["Payroll Manager", "Compensation and Benefits Specialist"],
    "People Development": ["Learning and Development Manager"],
    "Employee Support": ["Employee Relations Manager", "HR Operations Specialist"],
    "Business Management": ["Management Admin", "Senior Manager"],
    "Interview Panel": ["Technical Interviewer", "Panel Interviewer"],
    "Self Service": ["Employee"],
    "Candidate Portal": ["Candidate"],
}

ROLE_ALIASES = {
    "Root": "Super User",
    "Admin": "Management Admin",
    "Org Head": "Senior Manager",
    "Team Lead": "Senior Manager",
    "Member": "Employee",
}


def normalize_role(role):
    role = role or "Employee"
    return ROLE_ALIASES.get(role, role if role in HRMS_ROLES else "Employee")


def user_role(user):
    return normalize_role(user.get("hrms_role") or user.get("portal_role") or user.get("role")) if user else "Employee"


def role_permissions(role):
    role = normalize_role(role)
    candidate = role == "Candidate"
    super_user = role == "Super User"
    finance = super_user or role in ["Payroll Manager", "Compensation and Benefits Specialist"]
    hr_leadership = super_user or role in ["Management Admin", "HR Director", "HR Manager", "HR Business Partner"]
    recruiter = hr_leadership or role in ["HR Recruiter", "Talent Acquisition Specialist"]
    interviewer = recruiter or role in ["Technical Interviewer", "Panel Interviewer"]
    people_dev = super_user or role in ["Management Admin", "HR Director", "HR Manager", "HR Business Partner", "Learning and Development Manager"]
    employee_relations = super_user or role in ["Management Admin", "HR Director", "HR Manager", "Employee Relations Manager", "HR Operations Specialist"]
    team_manager = super_user or role in ["Management Admin", "HR Director", "HR Manager", "HR Business Partner", "Senior Manager"]
    internal_user = not candidate
    return {
        "is_super_user": super_user,
        "is_finance": finance,
        "is_hr_leadership": hr_leadership,
        "is_team_manager_role": team_manager,
        "can_manage_users": super_user,
        "can_manage_employees": super_user,
        "can_view_company_dashboard": super_user or hr_leadership,
        "can_view_recruitment": recruiter or interviewer,
        "can_view_candidate_process": candidate,
        "can_manage_recruitment": recruiter,
        "can_ai_screen_resumes": recruiter,
        "can_run_voice_interviews": interviewer,
        "can_assign_interviewers": recruiter,
        "can_review_recruitment": recruiter or interviewer,
        "can_view_team_dashboard": team_manager,
        "can_view_payroll": internal_user,
        "can_check_payroll_self": internal_user,
        "can_configure_payroll": finance,
        "can_soft_mark_payroll": finance,
        "can_process_payouts": finance,
        "can_confirm_team_payroll": team_manager,
        "can_view_employees": internal_user,
        "can_message_employees": internal_user,
        "can_view_performance": internal_user,
        "can_review_performance": people_dev or team_manager,
        "can_manage_performance_cycles": people_dev,
        "can_manage_learning": people_dev,
        "can_manage_employee_relations": employee_relations,
        "can_manage_leave": employee_relations or team_manager,
        "can_view_attendance": internal_user,
        "can_view_all_attendance": super_user or role in ["Management Admin", "HR Director", "HR Manager"],
        "can_manage_attendance_rules": super_user,
        "can_assign_managers": super_user,
        "can_review_attendance": employee_relations or team_manager,
        "can_schedule_attendance_meetings": employee_relations or team_manager,
        "can_view_attendance_reports": finance or employee_relations or team_manager,
        "can_view_self_service": internal_user,
        "can_customize_theme": True,
    }
