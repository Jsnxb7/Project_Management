from datetime import datetime, timezone
from pathlib import Path
import os
import secrets

from bson import ObjectId
from flask import Blueprint, current_app, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from app import bcrypt

from database.db import (
    users_collection,
    jobs_collection,
    applications_collection,
    resume_screening_collection,
    interview_sessions_collection,
    interview_rooms_collection,
    interview_messages_collection,
    recruitment_candidates_collection,
    employees_collection,
)
from services.ai_recruitment_service import extract_keywords, extract_resume_text, convert_resume_to_txt, screen_resume, evaluate_answer
from services.ai_interview_service import mark_room_created_for_ai
from services.hrms_service import role_permissions, user_role, to_object_id, primary_super_user_id
from utils.response import ok, fail, warn

recruitment_bp = Blueprint("recruitment_bp", __name__)

ALLOWED_RESUME_EXT = {".pdf", ".doc", ".docx", ".txt", ".tex", ".rtf", ".md"}
JOB_PROGRESS_STEPS = ["JD Created", "Open for Applications", "Applicants Screened", "Shortlist Ready", "Interview Process", "Final Selection"]
APP_PROGRESS_STEPS = ["Applied", "Screened", "Pending Review", "Shortlisted", "Candidate Account", "Interview Scheduled", "Interview Steps", "Selected"]


def now():
    return datetime.now(timezone.utc)


def current_user():
    user_id = to_object_id(get_jwt_identity())
    return users_collection.find_one({"_id": user_id, "is_active": True}) if user_id else None


def optional_current_user():
    try:
        identity = get_jwt_identity()
    except Exception:
        identity = None
    user_id = to_object_id(identity)
    return users_collection.find_one({"_id": user_id, "is_active": True}) if user_id else None


def require_perm(name):
    user = current_user()
    if not user:
        return None, fail("User not found", 404)
    if not role_permissions(user_role(user)).get(name):
        return user, warn(f"Warning: your role cannot perform this recruitment action.")
    return user, None


def _safe_float(value, default=70):
    try:
        return float(value)
    except Exception:
        return float(default)


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        raw = str(value).strip()
        if not raw:
            return None
        # datetime-local sends YYYY-MM-DDTHH:MM. Treat naive values as UTC for storage.
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _serialize_dt(value):
    return value.isoformat() if value and hasattr(value, "isoformat") else value


def _clean_csv_keywords(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value).replace("\n", ",").split(",") if x.strip()]


def _parse_user_ids(value):
    if not value:
        return []
    if isinstance(value, str):
        raw = [x.strip() for x in value.replace("\n", ",").split(",") if x.strip()]
    else:
        raw = list(value)
    ids = []
    seen = set()
    for item in raw:
        oid = to_object_id(item)
        if oid and str(oid) not in seen:
            ids.append(oid)
            seen.add(str(oid))
    return ids


def _id_list_strings(values):
    return [str(v) for v in values or [] if v]


def _generate_candidate_uid():
    while True:
        uid = "CAND-" + secrets.token_hex(3).upper()
        if not users_collection.find_one({"candidate_uid": uid}) and not recruitment_candidates_collection.find_one({"candidate_uid": uid}):
            return uid


def _generate_candidate_password():
    # Meets the existing password validator: 8+ chars with letters and numbers.
    return "Cand" + secrets.token_hex(4)


def _ensure_candidate_user(app_doc, created_by=None):
    """Create or link a limited candidate user for a shortlisted applicant."""
    email = (app_doc.get("candidate_email") or "").strip().lower()
    if not email:
        return None, None, "Candidate email is required before a candidate account can be created."

    now_value = now()
    user = users_collection.find_one({"email": email})
    temp_password = None
    candidate_uid = app_doc.get("candidate_uid") or _generate_candidate_uid()

    if user:
        # Do not downgrade internal HR users. Mark the account as candidate-linked only when safe.
        role = user_role(user)
        updates = {
            "candidate_uid": user.get("candidate_uid") or candidate_uid,
            "candidate_application_ids": list(set([*(user.get("candidate_application_ids") or []), app_doc["_id"]])),
            "candidate_job_ids": list(set([*(user.get("candidate_job_ids") or []), app_doc.get("job_id")])),
            "updated_at": now_value,
        }
        if role == "Employee":
            updates.update({"hrms_role": "Candidate", "portal_role": "Candidate", "role": "Candidate"})
        users_collection.update_one({"_id": user["_id"]}, {"$set": updates})
        user = users_collection.find_one({"_id": user["_id"]})
    else:
        temp_password = _generate_candidate_password()
        user_doc = {
            "name": app_doc.get("candidate_name") or "Candidate",
            "email": email,
            "password_hash": bcrypt.generate_password_hash(temp_password).decode("utf-8"),
            "profile_image": None,
            "hrms_role": "Candidate",
            "portal_role": "Candidate",
            "role": "Candidate",
            "candidate_uid": candidate_uid,
            "candidate_application_ids": [app_doc["_id"]],
            "candidate_job_ids": [app_doc.get("job_id")],
            "is_active": True,
            "created_by": created_by,
            "created_at": now_value,
            "updated_at": now_value,
            "last_login": None,
            "must_change_password": True,
        }
        res = users_collection.insert_one(user_doc)
        user_doc["_id"] = res.inserted_id
        user = user_doc

    recruitment_candidates_collection.update_one(
        {"candidate_email": email},
        {"$set": {
            "candidate_uid": user.get("candidate_uid") or candidate_uid,
            "candidate_user_id": user["_id"],
            "candidate_name": app_doc.get("candidate_name"),
            "candidate_email": email,
            "latest_application_id": app_doc["_id"],
            "latest_job_id": app_doc.get("job_id"),
            "status": app_doc.get("status"),
            "updated_at": now_value,
        }, "$setOnInsert": {"created_at": now_value}},
        upsert=True,
    )

    app_updates = {
        "candidate_user_id": user["_id"],
        "candidate_uid": user.get("candidate_uid") or candidate_uid,
        "candidate_login_email": user.get("email") or email,
        "candidate_account_created": True,
        "candidate_account_created_at": now_value,
        "updated_at": now_value,
    }
    if temp_password:
        app_updates["candidate_login_password"] = temp_password
        app_updates["candidate_password_note"] = "Temporary password generated when the candidate account was created."

    applications_collection.update_one(
        {"_id": app_doc["_id"]},
        {"$set": app_updates}
    )
    return user, temp_password, None


def _default_interview_steps(mode="AI Voice + Human Panel"):
    return [
        {"key": "account", "title": "Log in to candidate portal", "status": "Ready", "details": "Use the UID/email and temporary password shared by HR."},
        {"key": "room", "title": "Join assigned interview room", "status": "Pending", "details": "Open the interview room link at the scheduled time."},
        {"key": "chat", "title": "Use interview chat", "status": "Pending", "details": "Messages and notes appear in the room chat."},
        {"key": "voice", "title": "Complete AI voice interaction", "status": "Pending", "details": "STT/TTS will be wired later; transcript space is already available."},
        {"key": "panel", "title": mode, "status": "Pending", "details": "Human interviewer or panel review step."},
    ]


def _parse_process_steps(value, mode="AI Voice + Human Panel"):
    if not value:
        return _default_interview_steps(mode)
    if isinstance(value, list):
        steps = []
        for i, item in enumerate(value):
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or "").strip()
                if title:
                    steps.append({"key": item.get("key") or f"custom_{i+1}", "title": title, "status": item.get("status") or "Pending", "details": item.get("details") or ""})
            else:
                title = str(item).strip()
                if title:
                    steps.append({"key": f"custom_{i+1}", "title": title, "status": "Pending", "details": ""})
        return steps or _default_interview_steps(mode)
    raw = [x.strip() for x in str(value).replace("\r", "\n").split("\n") if x.strip()]
    return [{"key": f"custom_{i+1}", "title": line, "status": "Pending", "details": ""} for i, line in enumerate(raw)] or _default_interview_steps(mode)


def _application_has_interview(app_id):
    return interview_sessions_collection.count_documents({"application_id": app_id}) > 0


def _upload_resume(file):
    if not file or not file.filename:
        raise ValueError("Resume upload is required")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_RESUME_EXT:
        raise ValueError("Resume must be PDF, DOC, DOCX, TXT, TEX, RTF, or MD")
    upload_root = Path(current_app.config.get("UPLOAD_FOLDER", "static/uploads")) / "resumes"
    upload_root.mkdir(parents=True, exist_ok=True)
    safe = secure_filename(file.filename)
    stored_name = f"{secrets.token_hex(8)}_{safe}"
    stored_path = upload_root / stored_name
    file.save(stored_path)
    return safe, stored_path


def _convert_uploaded_resume(stored_path):
    """Normalize any supported resume upload to TXT before screening."""
    result = convert_resume_to_txt(stored_path)
    if not result.get("ok"):
        raise ValueError(
            "Could not convert this resume into readable text. Upload a text-based PDF, DOCX, DOC, TXT, TEX, RTF, or MD file. Scanned image-only PDFs need OCR before screening."
        )
    return result["text"], result["txt_path"], result


def _open_until_ok(job):
    open_until = job.get("open_until")
    if not open_until:
        return True
    if isinstance(open_until, str):
        open_until = _parse_dt(open_until)
    return bool(open_until and open_until >= now())


def _job_access_query(user, control=False):
    perms = role_permissions(user_role(user))
    if perms.get("is_super_user") or perms.get("can_view_company_dashboard"):
        return {}
    uid = user["_id"]
    access = [{"created_by": uid}, {"viewer_user_ids": uid}, {"controller_user_ids": uid}]
    if control:
        access = [{"created_by": uid}, {"controller_user_ids": uid}]
    return {"$or": access}


def _can_view_job(user, job):
    perms = role_permissions(user_role(user))
    if perms.get("is_super_user") or perms.get("can_view_company_dashboard"):
        return True
    uid = user["_id"]
    return job.get("created_by") == uid or uid in (job.get("viewer_user_ids") or []) or uid in (job.get("controller_user_ids") or [])


def _can_control_job(user, job):
    perms = role_permissions(user_role(user))
    if perms.get("is_super_user"):
        return True
    uid = user["_id"]
    return job.get("created_by") == uid or uid in (job.get("controller_user_ids") or [])


def _job_progress(job):
    job_id = job["_id"]
    total = applications_collection.count_documents({"job_id": job_id})
    screened = applications_collection.count_documents({"job_id": job_id, "final_score": {"$ne": None}})
    shortlisted = applications_collection.count_documents({"job_id": job_id, "status": {"$in": ["Shortlisted", "Interview Scheduled", "Selected"]}})
    interviews = applications_collection.count_documents({"job_id": job_id, "status": {"$in": ["Interview Scheduled", "Selected"]}})
    selected = applications_collection.count_documents({"job_id": job_id, "status": "Selected"})
    checks = [
        bool(job.get("description")),
        job.get("status") == "Open" and _open_until_ok(job),
        total > 0 and screened >= total,
        shortlisted > 0,
        interviews > 0,
        selected > 0,
    ]
    return {
        "steps": [{"name": name, "done": checks[i]} for i, name in enumerate(JOB_PROGRESS_STEPS)],
        "percent": round((sum(1 for x in checks if x) / len(checks)) * 100, 2),
        "counts": {"applications": total, "screened": screened, "shortlisted": shortlisted, "interviews": interviews, "selected": selected},
    }


def _application_progress(app):
    status = app.get("status", "Applied")
    review = app.get("review_status", "Pending Review")
    done = {
        "Applied": True,
        "Screened": app.get("final_score") is not None,
        "Pending Review": review in {"Pending Review", "Needs Review", "Shortlisted", "Interview Scheduled", "Selected", "Rejected", "On Hold"},
        "Shortlisted": status in {"Shortlisted", "Interview Scheduled", "Selected"},
        "Candidate Account": bool(app.get("candidate_account_created") or app.get("candidate_user_id")),
        "Interview Scheduled": status in {"Interview Scheduled", "Selected"} or bool(app.get("room_code")),
        "Interview Steps": bool(app.get("process_steps")),
        "Selected": status == "Selected",
    }
    return {"steps": [{"name": s, "done": bool(done.get(s))} for s in APP_PROGRESS_STEPS], "percent": round((sum(1 for v in done.values() if v) / len(APP_PROGRESS_STEPS)) * 100, 2)}


def serialize_job(job, include_counts=False, user=None):
    item = {
        "id": str(job["_id"]),
        "title": job.get("title"),
        "department": job.get("department"),
        "location": job.get("location"),
        "employment_type": job.get("employment_type"),
        "description": job.get("description"),
        "minimum_score": job.get("minimum_score", 70),
        "keywords": job.get("keywords", []),
        "status": job.get("status", "Open"),
        "open_until": _serialize_dt(job.get("open_until")),
        "is_public_open": job.get("status") == "Open" and _open_until_ok(job),
        "created_by": str(job.get("created_by")) if job.get("created_by") else None,
        "viewer_user_ids": _id_list_strings(job.get("viewer_user_ids")),
        "controller_user_ids": _id_list_strings(job.get("controller_user_ids")),
        "created_at": _serialize_dt(job.get("created_at")),
        "updated_at": _serialize_dt(job.get("updated_at")),
        "progress": _job_progress(job),
    }
    if user:
        item["can_control"] = _can_control_job(user, job)
        item["can_view"] = _can_view_job(user, job)
    if include_counts:
        item["application_count"] = applications_collection.count_documents({"job_id": job["_id"]})
        item["shortlisted_count"] = applications_collection.count_documents({"job_id": job["_id"], "status": {"$in": ["Shortlisted", "Interview Scheduled", "Selected"]}})
        item["review_count"] = applications_collection.count_documents({"job_id": job["_id"], "review_status": {"$in": ["Pending Review", "Needs Review"]}})
    return item


def serialize_application(app):
    return {
        "id": str(app["_id"]),
        "job_id": str(app.get("job_id")) if app.get("job_id") else None,
        "job_title": app.get("job_title"),
        "candidate_name": app.get("candidate_name"),
        "candidate_email": app.get("candidate_email"),
        "phone": app.get("phone"),
        "status": app.get("status", "Applied"),
        "review_status": app.get("review_status", "Pending Review"),
        "review_notes": app.get("review_notes", ""),
        "final_score": app.get("final_score"),
        "semantic_score": app.get("semantic_score"),
        "keyword_score": app.get("keyword_score"),
        "writing_score": app.get("writing_score"),
        "structure_score": app.get("structure_score"),
        "ats_score": app.get("ats_score"),
        "resume_filename": app.get("resume_filename"),
        "resume_txt_path": app.get("resume_txt_path"),
        "resume_text_char_count": app.get("resume_text_char_count"),
        "resume_text_word_count": app.get("resume_text_word_count"),
        "matched_keywords": app.get("matched_keywords", []),
        "missing_keywords": app.get("missing_keywords", []),
        "source": app.get("source", "Candidate Portal"),
        "progress": _application_progress(app),
        "created_at": _serialize_dt(app.get("created_at")),
        "reviewed_at": _serialize_dt(app.get("reviewed_at")),
        "candidate_uid": app.get("candidate_uid"),
        "candidate_login_email": app.get("candidate_login_email") or app.get("candidate_email"),
        "candidate_login_password": app.get("candidate_login_password"),
        "candidate_password_note": app.get("candidate_password_note") or ("Existing candidate password unchanged." if app.get("candidate_account_created") and not app.get("candidate_login_password") else None),
        "candidate_user_id": str(app.get("candidate_user_id")) if app.get("candidate_user_id") else None,
        "candidate_account_created": bool(app.get("candidate_account_created")),
        "room_code": app.get("room_code"),
        "scheduled_at": app.get("scheduled_at"),
        "interview_mode": app.get("interview_mode"),
        "process_steps": app.get("process_steps", []),
        "requires_interview_scheduling": app.get("status") == "Shortlisted" and not app.get("room_code"),
        "ai_interview_scheduled_at": app.get("ai_interview_scheduled_at"),
        "ai_interview_conducted": bool(app.get("ai_interview_conducted")),
        "ai_interview_room_configured": bool(app.get("ai_interview_room_configured")),
        "ai_interview_completed": bool(app.get("ai_interview_completed")),
        "ai_interview_score": app.get("ai_interview_score"),
        "ai_interview_result_id": str(app.get("ai_interview_result_id")) if app.get("ai_interview_result_id") else None,
        "ai_interview_transcript_id": str(app.get("ai_interview_transcript_id")) if app.get("ai_interview_transcript_id") else None,
        "ai_interview_recommendation": app.get("ai_interview_recommendation"),
        "ai_interview_status": app.get("ai_interview_status") or ("Conducted" if app.get("ai_interview_conducted") else "Pending"),
        "personal_interview_scheduled_at": app.get("personal_interview_scheduled_at"),
        "personal_interview_conducted": bool(app.get("personal_interview_conducted")),
        "personal_interview_status": app.get("personal_interview_status") or ("Conducted" if app.get("personal_interview_conducted") else "Pending"),
        "personal_interviewer_user_id": str(app.get("personal_interviewer_user_id")) if app.get("personal_interviewer_user_id") else None,
        "selection_stage": app.get("selection_stage") or "Application Review",
        "employee_created": bool(app.get("employee_created")),
        "employee_id": str(app.get("employee_id")) if app.get("employee_id") else None,
        "employee_code": app.get("employee_code"),
        "employee_login_email": app.get("employee_login_email"),
        "employee_login_password": app.get("employee_login_password"),
        "employee_joining_date": app.get("employee_joining_date"),
    }


def _serialize_report(report):
    return {
        "semantic_score": report.get("semantic_score"),
        "keyword_score": report.get("keyword_score"),
        "writing_score": report.get("writing_score"),
        "structure_score": report.get("structure_score"),
        "ats_score": report.get("ats_score"),
        "final_score": report.get("final_score"),
        "minimum_score": report.get("minimum_score"),
        "recommendation": report.get("recommendation"),
        "confidence": report.get("confidence"),
        "matched_keywords": report.get("matched_keywords", []),
        "missing_keywords": report.get("missing_keywords", []),
        "matched_keyword_details": report.get("matched_keyword_details", []),
        "highlighted_snippets": report.get("highlighted_snippets", []),
        "category_scores": report.get("category_scores", {}),
        "ats_checks": report.get("ats_checks", {}),
        "experience_years_detected": report.get("experience_years_detected"),
        "score_breakdown": report.get("score_breakdown", {}),
        "summary": report.get("summary"),
    }


def _pagination_args(default_limit=25, max_limit=100):
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(request.args.get("limit", default_limit))
    except (TypeError, ValueError):
        limit = default_limit
    limit = max(1, min(limit, max_limit))
    return page, limit, (page - 1) * limit


def _pagination_meta(total, page, limit):
    pages = max(1, (int(total or 0) + limit - 1) // limit)
    return {
        "page": page,
        "limit": limit,
        "total": int(total or 0),
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def _screen_and_store_application(job, candidate, resume_text, resume_filename, resume_path=None, resume_txt_path=None, conversion_info=None, source="Candidate Portal", created_by=None):
    text_for_screening = resume_text
    cover_note = candidate.get("cover_note") or ""
    if cover_note:
        text_for_screening = f"{resume_text}\n\nCover Note: {cover_note}".strip()

    result = screen_resume(job.get("description", ""), text_for_screening, job.get("keywords", []), job.get("minimum_score", 70), candidate.get("candidate_name"))
    status = "Shortlisted" if result.get("recommendation") == "Shortlist" else "Rejected"
    review_status = "Pending Review" if status == "Shortlisted" else "Auto Rejected"
    app_doc = {
        "job_id": job["_id"],
        "job_title": job.get("title"),
        "candidate_name": (candidate.get("candidate_name") or "Unknown Candidate").strip(),
        "candidate_email": (candidate.get("candidate_email") or "").strip().lower(),
        "phone": (candidate.get("phone") or "").strip(),
        "cover_note": cover_note,
        "resume_path": str(resume_path) if resume_path else None,
        "resume_txt_path": str(resume_txt_path) if resume_txt_path else None,
        "resume_filename": resume_filename,
        "resume_original_extension": Path(resume_path).suffix.lower() if resume_path else None,
        "resume_text": text_for_screening[:50000],
        "resume_text_char_count": len(resume_text or ""),
        "resume_text_word_count": len((resume_text or "").split()),
        "conversion_info": {k: v for k, v in (conversion_info or {}).items() if k != "text"},
        "status": status,
        "review_status": review_status,
        "final_score": result.get("final_score"),
        "semantic_score": result.get("semantic_score"),
        "keyword_score": result.get("keyword_score"),
        "writing_score": result.get("writing_score"),
        "structure_score": result.get("structure_score"),
        "ats_score": result.get("ats_score"),
        "matched_keywords": result.get("matched_keywords", []),
        "missing_keywords": result.get("missing_keywords", []),
        "source": source,
        "created_by": created_by,
        "created_at": now(),
        "updated_at": now(),
    }
    insert = applications_collection.insert_one(app_doc)
    result_doc = dict(result)
    result_doc.update({"application_id": insert.inserted_id, "job_id": job["_id"], "candidate_name": app_doc["candidate_name"], "candidate_email": app_doc["candidate_email"], "resume_filename": resume_filename, "source": source, "created_by": created_by, "created_at": now()})
    resume_screening_collection.insert_one(result_doc)
    app_doc["_id"] = insert.inserted_id
    return app_doc, result_doc


@recruitment_bp.get("/public/jobs")
def public_jobs():
    query = {"status": "Open", "$or": [{"open_until": {"$exists": False}}, {"open_until": None}, {"open_until": {"$gte": now()}}]}
    q = (request.args.get("q") or "").strip()
    if q:
        query["$and"] = [{"$or": [
            {"title": {"$regex": q, "$options": "i"}},
            {"department": {"$regex": q, "$options": "i"}},
            {"location": {"$regex": q, "$options": "i"}},
            {"employment_type": {"$regex": q, "$options": "i"}},
            {"keywords": {"$regex": q, "$options": "i"}},
        ]}]
    page, limit, skip = _pagination_args(default_limit=24, max_limit=50)
    total = jobs_collection.count_documents(query)
    jobs = list(jobs_collection.find(query).sort("created_at", -1).skip(skip).limit(limit))
    return ok("Open jobs fetched", {"jobs": [serialize_job(j) for j in jobs], "meta": _pagination_meta(total, page, limit)})


@recruitment_bp.post("/public/apply")
def public_apply():
    form = request.form
    job_id = to_object_id(form.get("job_id"))
    job = jobs_collection.find_one({"_id": job_id, "status": "Open"}) if job_id else None
    if not job or not _open_until_ok(job):
        return fail("This job is closed or unavailable")
    name = (form.get("candidate_name") or "").strip()
    email = (form.get("candidate_email") or "").strip().lower()
    phone = (form.get("phone") or "").strip()
    cover_note = (form.get("cover_note") or "").strip()
    if not name or not email:
        return fail("Candidate name and email are required")
    try:
        safe, stored_path = _upload_resume(request.files.get("resume"))
    except ValueError as exc:
        return fail(str(exc))
    try:
        resume_text, resume_txt_path, conversion = _convert_uploaded_resume(stored_path)
    except ValueError as exc:
        return fail(str(exc), 400)
    app_doc, result = _screen_and_store_application(job, {"candidate_name": name, "candidate_email": email, "phone": phone, "cover_note": cover_note}, resume_text, safe, stored_path, resume_txt_path, conversion, source="Candidate Portal")
    return ok("Application submitted and AI screening completed", {"application_id": str(app_doc["_id"]), "status": app_doc["status"], "score": result.get("final_score"), "matched_keywords": result.get("matched_keywords", []), "message": "Your profile has been received. The HR team will contact shortlisted applicants."}, 201)


@recruitment_bp.get("/users-options")
@jwt_required()
def recruitment_user_options():
    user, error = require_perm("can_manage_recruitment")
    if error:
        return error
    roles = ["Super User", "Management Admin", "HR Director", "HR Manager", "HR Business Partner", "HR Recruiter", "Talent Acquisition Specialist", "Technical Interviewer", "Panel Interviewer", "Senior Manager"]
    rows = users_collection.find({"is_active": True, "$or": [{"hrms_role": {"$in": roles}}, {"portal_role": {"$in": roles}}, {"role": {"$in": roles}}]}, {"name": 1, "email": 1, "hrms_role": 1, "portal_role": 1, "role": 1}).sort("name", 1).limit(500)
    return ok("Recruitment users fetched", {"users": [{"id": str(r["_id"]), "name": r.get("name") or r.get("email") or "User", "email": r.get("email"), "role": user_role(r)} for r in rows]})


@recruitment_bp.get("/jobs")
@jwt_required()
def list_jobs():
    user, error = require_perm("can_view_recruitment")
    if error:
        return error
    page, limit, skip = _pagination_args(default_limit=50, max_limit=100)
    include_counts = request.args.get("include_counts", "1") != "0"
    query = _job_access_query(user)
    total = jobs_collection.count_documents(query)
    jobs = list(jobs_collection.find(query).sort("created_at", -1).skip(skip).limit(limit))
    return ok("Jobs fetched", {"jobs": [serialize_job(j, include_counts=include_counts, user=user) for j in jobs], "meta": _pagination_meta(total, page, limit)})


@recruitment_bp.get("/jobs/<job_id>")
@jwt_required()
def get_job(job_id):
    user, error = require_perm("can_view_recruitment")
    if error:
        return error
    obj = to_object_id(job_id)
    job = jobs_collection.find_one({"_id": obj}) if obj else None
    if not job or not _can_view_job(user, job):
        return fail("Job not found or not shared with you", 404)
    return ok("Job fetched", {"job": serialize_job(job, include_counts=True, user=user)})


@recruitment_bp.post("/jobs")
@jwt_required()
def create_job():
    user, error = require_perm("can_manage_recruitment")
    if error:
        return error
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    if not title or not description:
        return fail("Job title and job description are required")
    keywords = _clean_csv_keywords(data.get("keywords")) or extract_keywords(description)
    viewer_ids = _parse_user_ids(data.get("viewer_user_ids"))
    controller_ids = _parse_user_ids(data.get("controller_user_ids"))
    doc = {
        "title": title,
        "department": (data.get("department") or "Recruitment").strip(),
        "location": (data.get("location") or "Hybrid").strip(),
        "employment_type": data.get("employment_type") or "Full-time",
        "description": description,
        "keywords": keywords,
        "minimum_score": _safe_float(data.get("minimum_score"), 70),
        "status": data.get("status") or "Open",
        "open_until": _parse_dt(data.get("open_until")),
        "viewer_user_ids": viewer_ids,
        "controller_user_ids": controller_ids,
        "created_by": user["_id"],
        "created_at": now(),
        "updated_at": now(),
    }
    res = jobs_collection.insert_one(doc)
    return ok("Job created", {"id": str(res.inserted_id), "keywords": keywords}, 201)


@recruitment_bp.patch("/jobs/<job_id>")
@jwt_required()
def update_job(job_id):
    user, error = require_perm("can_manage_recruitment")
    if error:
        return error
    obj = to_object_id(job_id)
    job = jobs_collection.find_one({"_id": obj}) if obj else None
    if not job or not _can_control_job(user, job):
        return fail("Job not found or you cannot control it", 404)
    data = request.get_json() or {}
    updates = {}
    for k in ["title", "department", "location", "employment_type", "description", "status"]:
        if k in data:
            updates[k] = (data.get(k) or "").strip() if isinstance(data.get(k), str) else data.get(k)
    if "keywords" in data:
        updates["keywords"] = _clean_csv_keywords(data.get("keywords"))
    if "description" in updates and not updates.get("keywords"):
        updates["keywords"] = extract_keywords(updates["description"])
    if "minimum_score" in data:
        updates["minimum_score"] = _safe_float(data.get("minimum_score"), 70)
    if "open_until" in data:
        updates["open_until"] = _parse_dt(data.get("open_until"))
    if "viewer_user_ids" in data:
        updates["viewer_user_ids"] = _parse_user_ids(data.get("viewer_user_ids"))
    if "controller_user_ids" in data:
        updates["controller_user_ids"] = _parse_user_ids(data.get("controller_user_ids"))
    updates["updated_at"] = now()
    jobs_collection.update_one({"_id": obj}, {"$set": updates})
    updated = jobs_collection.find_one({"_id": obj})
    return ok("Job updated", {"job": serialize_job(updated, include_counts=True, user=user)})


def _get_control_job_for_screen(user, job_id):
    job = jobs_collection.find_one({"_id": job_id}) if job_id else None
    if not job:
        return None, fail("Select a valid job before screening")
    if not _can_control_job(user, job):
        return None, fail("You can view this job but cannot control screening for it", 403)
    return job, None


@recruitment_bp.post("/screen/single")
@jwt_required()
def screen_single_resume():
    user, error = require_perm("can_ai_screen_resumes")
    if error:
        return error
    form = request.form
    job, bad = _get_control_job_for_screen(user, to_object_id(form.get("job_id")))
    if bad:
        return bad
    try:
        safe, stored_path = _upload_resume(request.files.get("resume"))
    except ValueError as exc:
        return fail(str(exc))
    name = (form.get("candidate_name") or Path(safe).stem.replace("_", " ")).strip()
    email = (form.get("candidate_email") or "").strip().lower()
    try:
        resume_text, resume_txt_path, conversion = _convert_uploaded_resume(stored_path)
    except ValueError as exc:
        return fail(str(exc), 400)
    app_doc, result = _screen_and_store_application(job, {"candidate_name": name, "candidate_email": email, "phone": form.get("phone") or "", "cover_note": form.get("cover_note") or ""}, resume_text, safe, stored_path, resume_txt_path, conversion, source="Internal Single Screening", created_by=user["_id"])
    return ok("Single resume screened", {"application": serialize_application(app_doc), "report": _serialize_report(result)}, 201)


@recruitment_bp.post("/screen/bulk")
@jwt_required()
def screen_bulk_resumes():
    user, error = require_perm("can_ai_screen_resumes")
    if error:
        return error
    form = request.form
    job, bad = _get_control_job_for_screen(user, to_object_id(form.get("job_id")))
    if bad:
        return bad
    files = request.files.getlist("resumes") or request.files.getlist("resume")
    if not files:
        return fail("Upload at least one resume file")
    created, errors = [], []
    for file in files[:50]:
        try:
            safe, stored_path = _upload_resume(file)
            resume_text, resume_txt_path, conversion = _convert_uploaded_resume(stored_path)
            candidate_name = Path(safe).stem.replace("_", " ").replace("-", " ").strip() or "Unknown Candidate"
            app_doc, result = _screen_and_store_application(job, {"candidate_name": candidate_name, "candidate_email": "", "phone": "", "cover_note": ""}, resume_text, safe, stored_path, resume_txt_path, conversion, source="Internal Bulk Screening", created_by=user["_id"])
            created.append({"application": serialize_application(app_doc), "report": _serialize_report(result)})
        except Exception as exc:
            errors.append({"filename": getattr(file, "filename", "unknown"), "error": str(exc)})
    return ok("Bulk screening completed", {"job": serialize_job(job, include_counts=True, user=user), "processed": len(created), "failed": len(errors), "results": created, "errors": errors}, 201)


@recruitment_bp.get("/applications")
@jwt_required()
def list_applications():
    user, error = require_perm("can_view_recruitment")
    if error:
        return error
    accessible_jobs = [j["_id"] for j in jobs_collection.find(_job_access_query(user), {"_id": 1})]
    query = {"job_id": {"$in": accessible_jobs}} if accessible_jobs else {"job_id": None}
    job_id = to_object_id(request.args.get("job_id"))
    if job_id:
        query["job_id"] = job_id if job_id in accessible_jobs or role_permissions(user_role(user)).get("is_super_user") else None
    if request.args.get("shortlisted") == "1":
        query["status"] = {"$in": ["Shortlisted", "Interview Scheduled", "Selected"]}
    review_status = request.args.get("review_status")
    if review_status:
        query["review_status"] = review_status
    page, limit, skip = _pagination_args(default_limit=24, max_limit=100)
    total = applications_collection.count_documents(query)
    projection = {"resume_text": 0, "conversion_info": 0}
    apps = list(applications_collection.find(query, projection).sort([("final_score", -1), ("created_at", -1)]).skip(skip).limit(limit))
    return ok("Applications fetched", {"applications": [serialize_application(a) for a in apps], "meta": _pagination_meta(total, page, limit)})


@recruitment_bp.get("/applications/<application_id>/report")
@jwt_required()
def application_report(application_id):
    user, error = require_perm("can_view_recruitment")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_view_job(user, job):
        return fail("Application report is not shared with you", 403)
    report = resume_screening_collection.find_one({"application_id": app["_id"]}) or {}
    return ok("AI screening report fetched", {"application": serialize_application(app), "job": serialize_job(job, include_counts=True, user=user), "report": _serialize_report(report), "resume_preview": (app.get("resume_text") or "")[:1200]})


@recruitment_bp.get("/applications/<application_id>/resume")
@jwt_required()
def download_resume(application_id):
    user, error = require_perm("can_view_recruitment")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_view_job(user, job):
        return fail("Resume is not shared with you", 403)
    path = app.get("resume_path")
    if not path or not os.path.exists(path):
        return fail("Resume file not found", 404)
    return send_file(path, as_attachment=True, download_name=app.get("resume_filename") or "resume")




@recruitment_bp.get("/applications/<application_id>/resume-text")
@jwt_required()
def download_resume_text(application_id):
    user, error = require_perm("can_view_recruitment")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_view_job(user, job):
        return fail("Converted resume text is not shared with you", 403)
    path = app.get("resume_txt_path")
    if not path or not os.path.exists(path):
        # Backfill older applications created before TXT normalization.
        original = app.get("resume_path")
        if not original or not os.path.exists(original):
            return fail("Converted resume text file not found", 404)
        try:
            conversion = convert_resume_to_txt(original)
            if not conversion.get("ok"):
                return fail(conversion.get("message") or "Could not convert resume to text", 400)
            path = conversion.get("txt_path")
            applications_collection.update_one(
                {"_id": app_id},
                {"$set": {
                    "resume_txt_path": path,
                    "resume_text": conversion.get("text", "")[:50000],
                    "resume_text_char_count": conversion.get("char_count"),
                    "resume_text_word_count": conversion.get("word_count"),
                    "conversion_info": {k: v for k, v in conversion.items() if k != "text"},
                    "updated_at": now(),
                }}
            )
        except Exception as exc:
            return fail(f"Could not create converted text file: {exc}", 400)
    filename = (Path(app.get("resume_filename") or "resume").stem or "resume") + "_converted.txt"
    return send_file(path, as_attachment=True, download_name=filename, mimetype="text/plain")


@recruitment_bp.patch("/applications/<application_id>/review")
@jwt_required()
def review_application(application_id):
    user, error = require_perm("can_review_recruitment")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_control_job(user, job):
        return fail("You cannot review applications for this job", 403)
    data = request.get_json() or {}
    decision = (data.get("decision") or "Needs Review").strip()
    allowed = {"Pending Review", "Needs Review", "Shortlisted", "Interview Scheduled", "Selected", "Rejected", "On Hold"}
    if decision not in allowed:
        return fail("Invalid review decision")
    updates = {"review_status": decision, "review_notes": (data.get("review_notes") or "").strip(), "reviewed_by": user["_id"], "reviewed_at": now(), "updated_at": now()}
    if decision in {"Shortlisted", "Selected", "Rejected", "On Hold", "Interview Scheduled"}:
        updates["status"] = decision
    applications_collection.update_one({"_id": app_id}, {"$set": updates})
    app = applications_collection.find_one({"_id": app_id})
    message = "Application review updated"
    payload = {"application": serialize_application(app)}
    if decision == "Shortlisted":
        candidate_user, temp_password, account_error = _ensure_candidate_user(app, user["_id"])
        if account_error:
            return fail(account_error, 400)
        app = applications_collection.find_one({"_id": app_id})
        payload["application"] = serialize_application(app)
        payload["candidate_credentials"] = {
            "candidate_uid": app.get("candidate_uid"),
            "candidate_email": app.get("candidate_login_email") or app.get("candidate_email"),
            "temporary_password": temp_password or app.get("candidate_login_password"),
            "password_note": "Temporary password generated when candidate account was created." if (temp_password or app.get("candidate_login_password")) else "Existing candidate password unchanged.",
        }
        if not _application_has_interview(app_id):
            payload["next_action"] = "schedule_interview"
            return warn("Candidate account created. Shortlisted applicant still needs interview dates and an assigned room.", payload)
    return ok(message, payload)


@recruitment_bp.delete("/applications/<application_id>/report")
@jwt_required()
def delete_application_report(application_id):
    user, error = require_perm("can_review_recruitment")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_control_job(user, job):
        return fail("You cannot delete this AI report", 403)
    resume_screening_collection.delete_many({"application_id": app_id})
    applications_collection.update_one({"_id": app_id}, {"$set": {
        "final_score": None,
        "semantic_score": None,
        "keyword_score": None,
        "writing_score": None,
        "structure_score": None,
        "ats_score": None,
        "matched_keywords": [],
        "missing_keywords": [],
        "review_status": "Needs Rescreening",
        "updated_at": now(),
    }})
    return ok("AI screening report deleted. Application kept for rescreening.")


@recruitment_bp.delete("/applications/<application_id>")
@jwt_required()
def delete_application(application_id):
    user, error = require_perm("can_review_recruitment")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_control_job(user, job):
        return fail("You cannot delete this application", 403)
    resume_screening_collection.delete_many({"application_id": app_id})
    interview_sessions_collection.update_many({"application_id": app_id}, {"$set": {"status": "Cancelled", "updated_at": now()}})
    applications_collection.delete_one({"_id": app_id})
    return ok("Application and linked AI reports deleted")


@recruitment_bp.post("/applications/<application_id>/assign-interview")
@jwt_required()
def assign_interview(application_id):
    user, error = require_perm("can_assign_interviewers")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_control_job(user, job):
        return fail("You cannot assign process for this job", 403)
    if app.get("status") not in {"Shortlisted", "Interview Scheduled", "Selected"}:
        return warn("Assigning interviews is recommended after shortlisting. Mark this applicant as Shortlisted first if this is intentional.")

    data = request.get_json() or {}
    interviewer_id = to_object_id(data.get("interviewer_user_id")) or user["_id"]
    panel_ids = _parse_user_ids(data.get("panel_user_ids"))
    mode = data.get("mode") or "AI Voice + Human Panel"
    room_code = app.get("room_code") or secrets.token_urlsafe(7).replace("-", "A").replace("_", "B")
    process_steps = _parse_process_steps(data.get("process_steps"), mode)

    candidate_user, temp_password, account_error = _ensure_candidate_user(app, user["_id"])
    if account_error:
        return fail(account_error, 400)
    app = applications_collection.find_one({"_id": app["_id"]}) or app
    login_password = temp_password or app.get("candidate_login_password")
    login_email = candidate_user.get("email") or app.get("candidate_email")

    existing = interview_sessions_collection.find_one({"application_id": app["_id"], "status": {"$ne": "Cancelled"}})
    session = {
        "application_id": app["_id"],
        "job_id": app.get("job_id"),
        "candidate_name": app.get("candidate_name"),
        "candidate_email": app.get("candidate_email"),
        "candidate_user_id": candidate_user["_id"],
        "candidate_uid": candidate_user.get("candidate_uid"),
        "candidate_login_email": login_email,
        "candidate_login_password": login_password,
        "candidate_password_note": "Temporary password generated when the candidate account was created." if login_password else "Existing candidate password unchanged.",
        "interviewer_user_id": interviewer_id,
        "panel_user_ids": panel_ids,
        "mode": mode,
        "status": "Scheduled",
        "room_code": room_code,
        "scheduled_at": data.get("scheduled_at"),
        "process_steps": process_steps,
        "created_by": user["_id"],
        "updated_at": now(),
    }
    if existing:
        interview_sessions_collection.update_one({"_id": existing["_id"]}, {"$set": session})
        session_id = existing["_id"]
    else:
        session["created_at"] = now()
        res = interview_sessions_collection.insert_one(session)
        session_id = res.inserted_id

    participants = [str(interviewer_id), *[str(x) for x in panel_ids], str(candidate_user["_id"]), app.get("candidate_email")]
    interview_rooms_collection.update_one(
        {"room_code": room_code},
        {"$set": {
            "session_id": session_id,
            "created_by": user["_id"],
            "participants": participants,
            "status": "open",
            "room_type": "ai_interview",
            "requires_ai_config": True,
            "requires_human_interviewer": False,
            "ai_interview_enabled": False,
            "ai_interview_config_status": "not_configured",
            "ai_interview_status": "not_started",
            "candidate_entry_locked": True,
            "candidate_entry_lock_reason": "AI interview room is not configured yet.",
            "updated_at": now(),
        }, "$setOnInsert": {"created_at": now()}},
        upsert=True,
    )
    mark_room_created_for_ai(room_code)
    applications_collection.update_one({"_id": app["_id"]}, {"$set": {
        "status": "Interview Scheduled",
        "review_status": "Interview Scheduled",
        "candidate_user_id": candidate_user["_id"],
        "candidate_uid": candidate_user.get("candidate_uid"),
        "candidate_login_email": login_email,
        "candidate_login_password": login_password,
        "candidate_password_note": "Temporary password generated when the candidate account was created." if login_password else "Existing candidate password unchanged.",
        "candidate_account_created": True,
        "interviewer_user_id": interviewer_id,
        "panel_user_ids": panel_ids,
        "scheduled_at": data.get("scheduled_at"),
        "room_code": room_code,
        "interview_mode": mode,
        "process_steps": process_steps,
        "updated_at": now(),
    }})
    credential_payload = {
        "candidate_uid": candidate_user.get("candidate_uid"),
        "candidate_email": login_email,
        "temporary_password": login_password,
        "password_note": "Temporary password generated when the candidate account was created." if login_password else "Existing candidate password unchanged.",
    }
    return ok("Candidate account and interview room assigned", {"session_id": str(session_id), "room_code": room_code, "join_url": f"/rooms/{room_code}/ai-interview", "controller_url": f"/rooms/{room_code}/configure-ai", "candidate_credentials": credential_payload, "process_steps": process_steps}, 201)




def _room_attended(app):
    if not app or not app.get("room_code"):
        return False
    if app.get("room_attended"):
        return True
    has_messages = interview_messages_collection.count_documents({"room_code": app.get("room_code")}, limit=1) > 0
    return bool(has_messages)


def _ensure_employee_code():
    total = employees_collection.count_documents({}) + 1
    while True:
        code = f"EMP-{total:04d}"
        if not employees_collection.find_one({"employee_code": code}):
            return code
        total += 1


@recruitment_bp.get("/second-round-candidates")
@jwt_required()
def second_round_candidates():
    user, error = require_perm("can_view_recruitment")
    if error:
        return error
    perms = role_permissions(user_role(user))
    jobs_query = {} if perms.get("is_super_user") or perms.get("can_manage_recruitment") else {"$or": [{"created_by": user["_id"]}, {"viewer_user_ids": user["_id"]}, {"controller_user_ids": user["_id"]}]}
    visible_job_ids = [j["_id"] for j in jobs_collection.find(jobs_query, {"_id": 1})]
    query = {
        "job_id": {"$in": visible_job_ids},
        "$or": [
            {"room_code": {"$ne": None}},
            {"status": {"$in": ["Interview Scheduled", "Selected"]}},
            {"selection_stage": {"$in": ["Second Round", "Final Review", "Employee Created"]}},
        ],
    }
    page, limit, skip = _pagination_args(default_limit=24, max_limit=100)
    total = applications_collection.count_documents(query)
    rows = list(applications_collection.find(query, {"resume_text": 0, "conversion_info": 0}).sort("updated_at", -1).skip(skip).limit(limit))
    items = []
    for app in rows:
        item = serialize_application(app)
        item["room_attended"] = _room_attended(app)
        item["second_round_ready"] = bool(item["room_attended"] or app.get("selection_stage") in {"Second Round", "Final Review", "Employee Created"})
        items.append(item)
    return ok("Second round candidates fetched", {"candidates": items, "meta": _pagination_meta(total, page, limit)})


@recruitment_bp.patch("/applications/<application_id>/schedule-rounds")
@jwt_required()
def schedule_candidate_rounds(application_id):
    user, error = require_perm("can_assign_interviewers")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_control_job(user, job):
        return fail("You cannot schedule interviews for this candidate", 403)
    data = request.get_json() or {}
    updates = {"updated_at": now(), "selection_stage": data.get("selection_stage") or app.get("selection_stage") or "Second Round"}
    for field in ["ai_interview_scheduled_at", "personal_interview_scheduled_at"]:
        if field in data:
            updates[field] = data.get(field)
    if "ai_interview_conducted" in data:
        updates["ai_interview_conducted"] = bool(data.get("ai_interview_conducted"))
        updates["ai_interview_status"] = "Conducted" if updates["ai_interview_conducted"] else "Pending"
    if "ai_interview_score" in data:
        updates["ai_interview_score"] = data.get("ai_interview_score")
    if "personal_interview_conducted" in data:
        updates["personal_interview_conducted"] = bool(data.get("personal_interview_conducted"))
        updates["personal_interview_status"] = "Conducted" if updates["personal_interview_conducted"] else "Pending"
    if data.get("personal_interviewer_user_id"):
        updates["personal_interviewer_user_id"] = to_object_id(data.get("personal_interviewer_user_id")) or user["_id"]
    if "personal_interview_notes" in data:
        updates["personal_interview_notes"] = (data.get("personal_interview_notes") or "").strip()
    applications_collection.update_one({"_id": app_id}, {"$set": updates})
    return ok("Interview schedule placeholders updated", {"application": serialize_application(applications_collection.find_one({"_id": app_id}))})


@recruitment_bp.post("/applications/<application_id>/create-employee")
@jwt_required()
def create_employee_from_candidate(application_id):
    user, error = require_perm("can_manage_employees")
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    job = jobs_collection.find_one({"_id": app.get("job_id")})
    if not job or not _can_control_job(user, job):
        return fail("You cannot select this candidate as employee", 403)
    data = request.get_json() or {}
    candidate_user, temp_password, account_error = _ensure_candidate_user(app, user["_id"])
    if account_error:
        return fail(account_error, 400)
    app = applications_collection.find_one({"_id": app_id}) or app
    employee_code = (data.get("employee_code") or app.get("employee_code") or _ensure_employee_code()).strip()
    existing_employee = employees_collection.find_one({"$or": [{"user_id": candidate_user["_id"]}, {"email": candidate_user.get("email")}]})
    manager_ids = _parse_user_ids(data.get("manager_ids") or [])
    if not manager_ids:
        manager_id = to_object_id(data.get("manager_id")) or primary_super_user_id(exclude_user_id=candidate_user["_id"])
        manager_ids = [manager_id] if manager_id else []
    manager_id = manager_ids[0] if manager_ids else None
    employee_login_password = data.get("employee_login_password") or _generate_candidate_password()
    now_value = now()
    employee_doc = {
        "user_id": candidate_user["_id"],
        "employee_code": employee_code,
        "name": (data.get("name") or app.get("candidate_name") or candidate_user.get("name") or "Employee").strip(),
        "email": (data.get("email") or candidate_user.get("email") or app.get("candidate_email") or "").strip().lower(),
        "phone": (data.get("phone") or app.get("phone") or "").strip(),
        "department": (data.get("department") or job.get("department") or "Unassigned").strip(),
        "designation": (data.get("designation") or job.get("title") or "Employee").strip(),
        "joining_date": data.get("joining_date") or now_value,
        "employment_status": data.get("employment_status") or "Active",
        "manager_id": manager_id,
        "manager_ids": manager_ids,
        "manager_status": "assigned" if manager_ids else "missing",
        "documents": data.get("documents") or [],
        "salary": data.get("salary") or {},
        "work_history": data.get("work_history") or [{"title": "Converted from recruitment", "application_id": app_id, "at": now_value}],
        "source": "Recruitment Selection",
        "candidate_application_id": app_id,
        "created_by": user["_id"],
        "updated_at": now_value,
    }
    if existing_employee:
        employee_doc["created_at"] = existing_employee.get("created_at") or now_value
        employees_collection.update_one({"_id": existing_employee["_id"]}, {"$set": employee_doc})
        employee_id = existing_employee["_id"]
    else:
        employee_doc["created_at"] = now_value
        result = employees_collection.insert_one(employee_doc)
        employee_id = result.inserted_id
    users_collection.update_one({"_id": candidate_user["_id"]}, {"$set": {
        "employee_id": employee_id,
        "employee_code": employee_code,
        "employee_login_email": employee_doc["email"],
        "employee_temp_password": employee_login_password,
        "candidate_selected": True,
        "updated_at": now_value,
    }})
    applications_collection.update_one({"_id": app_id}, {"$set": {
        "status": "Selected",
        "review_status": "Selected",
        "selection_stage": "Employee Created",
        "employee_created": True,
        "employee_id": employee_id,
        "employee_code": employee_code,
        "employee_login_email": employee_doc["email"],
        "employee_login_password": employee_login_password,
        "employee_joining_date": employee_doc["joining_date"],
        "updated_at": now_value,
    }})
    return ok("Candidate selected and employee profile created", {"application": serialize_application(applications_collection.find_one({"_id": app_id})), "employee_id": str(employee_id), "employee_code": employee_code, "employee_login_email": employee_doc["email"], "employee_login_password": employee_login_password}, 201)

@recruitment_bp.get("/interviews")
@jwt_required()
def list_interviews():
    user, error = require_perm("can_run_voice_interviews")
    if error:
        return error
    perms = role_permissions(user_role(user))
    query = {} if perms.get("is_super_user") or perms.get("can_manage_recruitment") else {"$or": [{"interviewer_user_id": user["_id"]}, {"panel_user_ids": user["_id"]}]}
    page, limit, skip = _pagination_args(default_limit=24, max_limit=100)
    total = interview_sessions_collection.count_documents(query)
    rows = list(interview_sessions_collection.find(query).sort("created_at", -1).skip(skip).limit(limit))
    room_codes = [r.get("room_code") for r in rows if r.get("room_code")]
    rooms = {room.get("room_code"): room for room in interview_rooms_collection.find({"room_code": {"$in": room_codes}})} if room_codes else {}
    payload = []
    for r in rows:
        room = rooms.get(r.get("room_code"), {})
        payload.append({
            "id": str(r["_id"]),
            "candidate_name": r.get("candidate_name"),
            "candidate_email": r.get("candidate_email"),
            "mode": r.get("mode"),
            "status": r.get("status"),
            "room_code": r.get("room_code"),
            "scheduled_at": r.get("scheduled_at"),
            "room_type": room.get("room_type") or r.get("room_type"),
            "current_interview_phase": room.get("current_interview_phase") or r.get("current_interview_phase"),
            "ai_interview_config_status": room.get("ai_interview_config_status"),
            "ai_interview_status": room.get("ai_interview_status"),
            "candidate_entry_locked": room.get("candidate_entry_locked"),
        })
    return ok("Interviews fetched", {"interviews": payload, "meta": _pagination_meta(total, page, limit)})


@recruitment_bp.post("/ai/voice-answer")
@jwt_required(optional=True)
def voice_answer_eval():
    data = request.get_json() or {}
    result = evaluate_answer(data.get("question") or "Tell me about your relevant experience.", data.get("expected_answer") or data.get("rubric") or data.get("job_context") or "", data.get("candidate_answer") or data.get("transcript") or "", data.get("keywords"))
    return ok("Voice transcript evaluated", {"evaluation": result})



@recruitment_bp.get("/candidate/process")
@jwt_required()
def candidate_process():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    has_candidate_link = bool(user.get("candidate_application_ids") or user.get("candidate_uid") or user.get("candidate_selected"))
    if user_role(user) != "Candidate" and not role_permissions(user_role(user)).get("is_super_user") and not has_candidate_link:
        return fail("This page is only for candidate accounts", 403)
    is_candidate = user_role(user) == "Candidate" or has_candidate_link
    query = {"candidate_user_id": user["_id"]}
    if user.get("email"):
        query = {"$or": [{"candidate_user_id": user["_id"]}, {"candidate_email": user.get("email")}]}
    apps = list(applications_collection.find(query).sort("created_at", -1).limit(20))
    job_ids = [a.get("job_id") for a in apps if a.get("job_id")]
    jobs = {j["_id"]: j for j in jobs_collection.find({"_id": {"$in": job_ids}})} if job_ids else {}
    sessions = list(interview_sessions_collection.find({"$or": [{"candidate_user_id": user["_id"]}, {"candidate_email": user.get("email")}]}).sort("created_at", -1).limit(20))
    room_codes = list({x for x in [*[a.get("room_code") for a in apps], *[s.get("room_code") for s in sessions]] if x})
    rooms = {room.get("room_code"): room for room in interview_rooms_collection.find({"room_code": {"$in": room_codes}})} if room_codes else {}
    def candidate_join_url(room_code):
        room = rooms.get(room_code) or {}
        phase = room.get("current_interview_phase") or room.get("room_type")
        if phase in {"human_interview", "personal_interview", "hr_interview"} or room.get("room_type") in {"human_interview", "personal_interview", "hr_interview"}:
            return f"/rooms/{room_code}/human-interview"
        return f"/rooms/{room_code}/ai-interview"
    if is_candidate:
        return ok("Candidate process fetched", {
            "candidate_view": True,
            "applications": [{
                "id": str(a["_id"]),
                "job_title": a.get("job_title") or (jobs.get(a.get("job_id")) or {}).get("title"),
                "room_code": a.get("room_code"),
                "join_url": candidate_join_url(a.get("room_code")) if a.get("room_code") else None,
                "scheduled_at": a.get("scheduled_at"),
                "interview_mode": a.get("interview_mode"),
                "process_steps": a.get("process_steps", []),
                "status": a.get("status"),
                "ai_interview_scheduled_at": a.get("ai_interview_scheduled_at"),
                "ai_interview_conducted": bool(a.get("ai_interview_conducted")),
                "personal_interview_scheduled_at": a.get("personal_interview_scheduled_at"),
                "personal_interview_conducted": bool(a.get("personal_interview_conducted")),
                "employee_created": bool(a.get("employee_created")),
                "employee_code": a.get("employee_code"),
                "employee_login_email": a.get("employee_login_email"),
                "employee_login_password": a.get("employee_login_password"),
            } for a in apps],
            "interviews": [{
                "id": str(r["_id"]),
                "room_code": r.get("room_code"),
                "join_url": candidate_join_url(r.get("room_code")),
                "scheduled_at": r.get("scheduled_at"),
                "mode": r.get("mode"),
                "process_steps": r.get("process_steps", []),
            } for r in sessions],
        })
    return ok("Candidate process fetched", {
        "candidate_view": False,
        "candidate": {"name": user.get("name"), "email": user.get("email"), "candidate_uid": user.get("candidate_uid")},
        "applications": [{**serialize_application(a), "job": serialize_job(jobs.get(a.get("job_id")), user=user) if jobs.get(a.get("job_id")) else None} for a in apps],
        "interviews": [{"id": str(r["_id"]), "room_code": r.get("room_code"), "join_url": candidate_join_url(r.get("room_code")), "scheduled_at": r.get("scheduled_at"), "status": r.get("status"), "mode": r.get("mode"), "process_steps": r.get("process_steps", [])} for r in sessions],
    })


@recruitment_bp.get("/rooms/<room_code>/details")
@jwt_required(optional=True)
def room_details(room_code):
    room = interview_rooms_collection.find_one({"room_code": room_code})
    if not room:
        return fail("Interview room not found", 404)
    session = interview_sessions_collection.find_one({"_id": room.get("session_id")}) or {}
    app = applications_collection.find_one({"_id": session.get("application_id")}) if session.get("application_id") else None
    job = jobs_collection.find_one({"_id": session.get("job_id")}) if session.get("job_id") else None
    viewer = optional_current_user()
    viewer_role = user_role(viewer) if viewer else "Guest"
    viewer_is_candidate = viewer_role == "Candidate"
    can_view_credentials = bool(viewer and job and not viewer_is_candidate and _can_view_job(viewer, job))
    session_payload = {
        "candidate_name": session.get("candidate_name"),
        "candidate_email": None if viewer_is_candidate else session.get("candidate_email"),
        "candidate_uid": None if viewer_is_candidate else session.get("candidate_uid"),
        "mode": session.get("mode"),
        "status": session.get("status"),
        "scheduled_at": session.get("scheduled_at"),
        "process_steps": session.get("process_steps", []),
    }
    if can_view_credentials:
        session_payload["candidate_credentials"] = {
            "candidate_uid": session.get("candidate_uid") or (app or {}).get("candidate_uid"),
            "candidate_email": session.get("candidate_login_email") or session.get("candidate_email") or (app or {}).get("candidate_login_email") or (app or {}).get("candidate_email"),
            "temporary_password": session.get("candidate_login_password") or (app or {}).get("candidate_login_password"),
            "password_note": session.get("candidate_password_note") or (app or {}).get("candidate_password_note") or "Existing candidate password unchanged.",
        }
    return ok("Interview room details fetched", {
        "room": {
            "room_code": room_code,
            "status": room.get("status"),
            "participants": room.get("participants", []),
            "room_type": room.get("room_type"),
            "heading": room.get("heading"),
            "ai_interview_enabled": room.get("ai_interview_enabled"),
            "ai_interview_config_status": room.get("ai_interview_config_status"),
            "ai_interview_status": room.get("ai_interview_status"),
            "candidate_entry_locked": room.get("candidate_entry_locked"),
            "candidate_entry_lock_reason": room.get("candidate_entry_lock_reason"),
            "ai_config_id": str(room.get("ai_config_id")) if room.get("ai_config_id") else None,
            "ai_transcript_id": str(room.get("ai_transcript_id")) if room.get("ai_transcript_id") else None,
            "ai_result_id": str(room.get("ai_result_id")) if room.get("ai_result_id") else None,
        },
        "session": session_payload,
        "application": None if viewer_is_candidate else (serialize_application(app) if app else None),
        "job": None if viewer_is_candidate else (serialize_job(job) if job else None),
        "viewer_role": viewer_role,
        "candidate_view": viewer_is_candidate,
    })


@recruitment_bp.get("/rooms/<room_code>/messages")
@jwt_required(optional=True)
def room_messages(room_code):
    room = interview_rooms_collection.find_one({"room_code": room_code})
    if not room:
        return fail("Interview room not found", 404)
    rows = list(interview_messages_collection.find({"room_code": room_code}).sort("created_at", 1).limit(200))
    return ok("Room messages fetched", {"messages": [{"sender": r.get("sender"), "message": r.get("message"), "kind": r.get("kind", "chat"), "created_at": _serialize_dt(r.get("created_at"))} for r in rows]})


@recruitment_bp.post("/rooms/<room_code>/messages")
@jwt_required(optional=True)
def post_room_message(room_code):
    room = interview_rooms_collection.find_one({"room_code": room_code})
    if not room:
        return fail("Interview room not found", 404)
    data = request.get_json() or {}
    sender = (data.get("sender") or "Participant").strip()[:80]
    message = (data.get("message") or "").strip()
    if not message:
        return fail("Message is required")
    interview_messages_collection.insert_one({"room_code": room_code, "sender": sender, "message": message, "kind": data.get("kind") or "chat", "created_at": now()})
    return ok("Message sent")
