from flask import Blueprint, render_template, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt, verify_jwt_in_request

interview_pages_v2_bp = Blueprint("interview_pages_v2", __name__)


def _claims_role():
    try:
        verify_jwt_in_request(optional=True)
        claims = get_jwt() or {}
        return claims.get("role") or claims.get("portal_role") or claims.get("type") or ""
    except Exception:
        return ""


def _is_controller_role(role):
    return str(role).lower().replace(" ", "_") in {
        "super_user",
        "superuser",
        "controller",
        "admin",
        "hr",
        "hr_staff",
        "org_head",
        "management_admin",
        "hr_director",
        "hr_manager",
        "hr_business_partner",
        "hr_recruiter",
        "talent_acquisition_specialist",
        "technical_interviewer",
        "panel_interviewer",
        "senior_manager",
    }


@interview_pages_v2_bp.get("/rooms/<room_code>/configure-ai")
@jwt_required(optional=True)
def configure_ai_room_page(room_code):
    # Page-level guard is intentionally light because API routes still enforce permissions.
    # This keeps direct navigation usable in local dev while protecting sensitive data through APIs.
    role = _claims_role()
    if role and not _is_controller_role(role):
        return redirect(url_for("interview_pages_v2.ai_interview_candidate_page", room_code=room_code))
    return render_template("ai_room_config.html", room_code=room_code)


@interview_pages_v2_bp.get("/rooms/<room_code>/ai-interview")
@jwt_required(optional=True)
def ai_interview_candidate_page(room_code):
    return render_template("ai_interview_candidate.html", room_code=room_code)


@interview_pages_v2_bp.get("/rooms/<room_code>/human-interview")
@jwt_required(optional=True)
def human_interview_room_page(room_code):
    return render_template("human_interview_room.html", room_code=room_code)


# Compatibility redirects from older patched pages.
@interview_pages_v2_bp.get("/interview-room/<room_code>")
@jwt_required(optional=True)
def old_interview_room_redirect(room_code):
    role = _claims_role()
    if _is_controller_role(role):
        return redirect(url_for("interview_pages_v2.configure_ai_room_page", room_code=room_code))
    return redirect(url_for("interview_pages_v2.ai_interview_candidate_page", room_code=room_code))
