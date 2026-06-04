from datetime import datetime, timezone
from pathlib import Path
import os
import secrets

from bson import ObjectId
from flask import Blueprint, current_app, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from database.db import (
    users_collection,
    jobs_collection,
    applications_collection,
    resume_screening_collection,
    interview_sessions_collection,
    interview_rooms_collection,
    interview_messages_collection,
)
from services.ai_recruitment_service import extract_keywords, extract_resume_text, screen_resume, evaluate_answer
from services.hrms_service import role_permissions, user_role, to_object_id, normalize_role
from utils.response import ok, fail, warn

recruitment_bp = Blueprint("recruitment_bp", __name__)

ALLOWED_RESUME_EXT = {".pdf", ".doc", ".docx", ".txt"}


def now():
    return datetime.now(timezone.utc)


def current_user():
    user_id = to_object_id(get_jwt_identity())
    return users_collection.find_one({"_id": user_id}) if user_id else None


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


def _clean_csv_keywords(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value).replace("\n", ",").split(",") if x.strip()]


def _upload_resume(file):
    if not file or not file.filename:
        raise ValueError("Resume upload is required")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_RESUME_EXT:
        raise ValueError("Resume must be PDF, DOC, DOCX, or TXT")
    upload_root = Path(current_app.config.get("UPLOAD_FOLDER", "static/uploads")) / "resumes"
    upload_root.mkdir(parents=True, exist_ok=True)
    safe = secure_filename(file.filename)
    stored_name = f"{secrets.token_hex(8)}_{safe}"
    stored_path = upload_root / stored_name
    file.save(stored_path)
    return safe, stored_path


def _serialize_dt(value):
    return value.isoformat() if value and hasattr(value, "isoformat") else value


def _oid_list(values):
    clean = []
    for value in values or []:
        obj = to_object_id(value)
        if obj and obj not in clean:
            clean.append(obj)
    return clean


def _same_oid(a, b):
    return str(a) == str(b) if a and b else False


def _name_for_user_id(user_id):
    obj = to_object_id(user_id)
    if not obj:
        return ""
    user = users_collection.find_one({"_id": obj}, {"name": 1, "email": 1, "hrms_role": 1, "role": 1})
    if not user:
        return ""
    return user.get("name") or user.get("email") or str(obj)


def _user_ref(user):
    if not user:
        return None
    return {
        "id": str(user.get("_id")),
        "name": user.get("name") or user.get("email") or "User",
        "email": user.get("email", ""),
        "role": user_role(user),
    }


def _job_viewers(job):
    return [str(x) for x in job.get("viewer_user_ids", []) if x]


def _job_controllers(job):
    return [str(x) for x in job.get("controller_user_ids", []) if x]


def _is_job_creator(user, job):
    return bool(user and job and _same_oid(job.get("created_by"), user.get("_id")))


def _is_job_viewer(user, job):
    if not user or not job:
        return False
    uid = str(user.get("_id"))
    return uid in _job_viewers(job) or uid in _job_controllers(job) or _is_job_creator(user, job)


def _is_job_controller(user, job):
    if not user or not job:
        return False
    perms = role_permissions(user_role(user))
    if perms.get("is_super_user"):
        return True
    uid = str(user.get("_id"))
    return uid in _job_controllers(job) or _is_job_creator(user, job)


def _job_access_query(user):
    perms = role_permissions(user_role(user))
    if perms.get("is_super_user"):
        return {}
    uid = user.get("_id")
    return {"$or": [
        {"created_by": uid},
        {"viewer_user_ids": uid},
        {"controller_user_ids": uid},
    ]}


def _job_ids_user_can_see(user):
    return [j["_id"] for j in jobs_collection.find(_job_access_query(user), {"_id": 1})]


def _require_recruitment_visibility():
    user = current_user()
    if not user:
        return None, fail("User not found", 404)
    perms = role_permissions(user_role(user))
    if perms.get("can_view_recruitment") or perms.get("is_super_user"):
        return user, None
    # Non-HR users may still see recruitment pages if a job was explicitly shared with them.
    if jobs_collection.count_documents(_job_access_query(user), limit=1):
        return user, None
    return user, warn("Warning: no recruitment jobs are shared with your account.")


def _job_progress(job):
    total = applications_collection.count_documents({"job_id": job["_id"]})
    screened = applications_collection.count_documents({"job_id": job["_id"], "final_score": {"$ne": None}})
    shortlisted = applications_collection.count_documents({"job_id": job["_id"], "status": {"$in": ["Shortlisted", "Interview Scheduled", "Selected"]}})
    interviews = applications_collection.count_documents({"job_id": job["_id"], "status": {"$in": ["Interview Scheduled", "Selected"]}})
    selected = applications_collection.count_documents({"job_id": job["_id"], "status": "Selected"})
    stages = [
        {"key": "created", "label": "JD Created", "done": True},
        {"key": "screening", "label": "Applicants Screened", "done": screened > 0, "count": screened},
        {"key": "shortlist", "label": "Shortlist Ready", "done": shortlisted > 0, "count": shortlisted},
        {"key": "interview", "label": "Interview Process", "done": interviews > 0, "count": interviews},
        {"key": "selection", "label": "Final Selection", "done": selected > 0, "count": selected},
    ]
    percent = round(sum(1 for s in stages if s.get("done")) / len(stages) * 100)
    return {"percent": percent, "total_applications": total, "screened": screened, "shortlisted": shortlisted, "interviews": interviews, "selected": selected, "stages": stages}


APPLICATION_STAGE_ORDER = [
    "Applied",
    "Screened",
    "Pending Review",
    "Shortlisted",
    "Interview Scheduled",
    "Selected",
]


def _application_progress(app):
    status = app.get("status") or "Applied"
    review = app.get("review_status") or "Pending Review"
    current = status if status in APPLICATION_STAGE_ORDER else review
    if status == "Rejected" or review == "Auto Rejected":
        return {"percent": 100, "current": status or review, "stages": [{"label": "Applied", "done": True}, {"label": "Screened", "done": bool(app.get("final_score") is not None)}, {"label": "Rejected", "done": True}]}
    idx = APPLICATION_STAGE_ORDER.index(current) if current in APPLICATION_STAGE_ORDER else 2
    stages = [{"label": label, "done": i <= idx} for i, label in enumerate(APPLICATION_STAGE_ORDER)]
    return {"percent": round((idx + 1) / len(APPLICATION_STAGE_ORDER) * 100), "current": current, "stages": stages}


def _can_view_application(user, app):
    if role_permissions(user_role(user)).get("is_super_user"):
        return True
    job = jobs_collection.find_one({"_id": app.get("job_id")}) if app.get("job_id") else None
    return _is_job_viewer(user, job)


def _can_control_application(user, app):
    if role_permissions(user_role(user)).get("is_super_user"):
        return True
    job = jobs_collection.find_one({"_id": app.get("job_id")}) if app.get("job_id") else None
    return _is_job_controller(user, job)


def serialize_job(job, include_counts=False, user=None):
    creator_name = _name_for_user_id(job.get("created_by")) if job.get("created_by") else ""
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
        "created_by": str(job.get("created_by")) if job.get("created_by") else None,
        "created_by_name": creator_name,
        "viewer_user_ids": _job_viewers(job),
        "controller_user_ids": _job_controllers(job),
        "can_control": _is_job_controller(user, job) if user else False,
        "can_view": _is_job_viewer(user, job) if user else False,
        "progress": _job_progress(job),
        "created_at": _serialize_dt(job.get("created_at")),
        "updated_at": _serialize_dt(job.get("updated_at")),
    }
    if include_counts:
        item["application_count"] = applications_collection.count_documents({"job_id": job["_id"]})
        item["shortlisted_count"] = applications_collection.count_documents({"job_id": job["_id"], "status": {"$in": ["Shortlisted", "Interview Scheduled", "Selected"]}})
        item["review_count"] = applications_collection.count_documents({"job_id": job["_id"], "review_status": {"$in": ["Pending Review", "Needs Review"]}})
    return item

def serialize_application(app, user=None):
    can_control = _can_control_application(user, app) if user else False
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
        "resume_filename": app.get("resume_filename"),
        "has_resume": bool(app.get("resume_path") or app.get("resume_text")),
        "matched_keywords": app.get("matched_keywords", []),
        "missing_keywords": app.get("missing_keywords", []),
        "source": app.get("source", "Candidate Portal"),
        "progress": _application_progress(app),
        "can_control": can_control,
        "created_at": _serialize_dt(app.get("created_at")),
        "reviewed_at": _serialize_dt(app.get("reviewed_at")),
    }

def _screen_and_store_application(job, candidate, resume_text, resume_filename, resume_path=None, source="Candidate Portal", created_by=None):
    text_for_screening = resume_text
    cover_note = candidate.get("cover_note") or ""
    if cover_note:
        text_for_screening = f"{resume_text}\n\nCover Note: {cover_note}".strip()

    result = screen_resume(
        job.get("description", ""),
        text_for_screening,
        job.get("keywords", []),
        job.get("minimum_score", 70),
        candidate.get("candidate_name"),
    )
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
        "resume_filename": resume_filename,
        "resume_text": text_for_screening[:50000],
        "status": status,
        "review_status": review_status,
        "final_score": result.get("final_score"),
        "semantic_score": result.get("semantic_score"),
        "keyword_score": result.get("keyword_score"),
        "writing_score": result.get("writing_score"),
        "structure_score": result.get("structure_score"),
        "matched_keywords": result.get("matched_keywords", []),
        "missing_keywords": result.get("missing_keywords", []),
        "source": source,
        "created_by": created_by,
        "created_at": now(),
        "updated_at": now(),
    }
    insert = applications_collection.insert_one(app_doc)
    result_doc = dict(result)
    result_doc.update({
        "application_id": insert.inserted_id,
        "job_id": job["_id"],
        "candidate_name": app_doc["candidate_name"],
        "candidate_email": app_doc["candidate_email"],
        "resume_filename": resume_filename,
        "source": source,
        "created_by": created_by,
        "created_at": now(),
    })
    resume_screening_collection.insert_one(result_doc)
    app_doc["_id"] = insert.inserted_id
    return app_doc, result_doc


@recruitment_bp.get("/access-users")
@jwt_required()
def recruitment_access_users():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    # Only users that can create/control jobs should assign job visibility.
    if not role_permissions(user_role(user)).get("can_manage_recruitment") and not role_permissions(user_role(user)).get("is_super_user"):
        return warn("Warning: your role cannot share recruitment jobs.")
    rows = list(users_collection.find({"is_active": {"$ne": False}}, {"name": 1, "email": 1, "hrms_role": 1, "role": 1, "portal_role": 1}).sort("name", 1).limit(500))
    return ok("Recruitment access users fetched", {"users": [_user_ref(r) for r in rows if str(r.get("_id")) != str(user.get("_id"))]})


@recruitment_bp.get("/public/jobs")
def public_jobs():
    jobs = list(jobs_collection.find({"status": "Open"}).sort("created_at", -1).limit(50))
    return ok("Open jobs fetched", {"jobs": [serialize_job(j) for j in jobs]})


@recruitment_bp.post("/public/apply")
def public_apply():
    form = request.form
    job_id = to_object_id(form.get("job_id"))
    job = jobs_collection.find_one({"_id": job_id, "status": "Open"}) if job_id else None
    if not job:
        return fail("Open job is required")
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
    resume_text = extract_resume_text(stored_path)
    app_doc, result = _screen_and_store_application(
        job,
        {"candidate_name": name, "candidate_email": email, "phone": phone, "cover_note": cover_note},
        resume_text,
        safe,
        stored_path,
        source="Candidate Portal",
    )
    return ok("Application submitted and AI screening completed", {
        "application_id": str(app_doc["_id"]),
        "status": app_doc["status"],
        "score": result.get("final_score"),
        "matched_keywords": result.get("matched_keywords", []),
        "message": "Your profile has been received. The HR team will contact shortlisted applicants."
    }, 201)


@recruitment_bp.get("/jobs")
@jwt_required()
def list_jobs():
    user, error = _require_recruitment_visibility()
    if error:
        return error
    jobs = list(jobs_collection.find(_job_access_query(user)).sort("created_at", -1).limit(100))
    return ok("Jobs fetched", {"jobs": [serialize_job(j, include_counts=True, user=user) for j in jobs]})


@recruitment_bp.get("/jobs/<job_id>")
@jwt_required()
def get_job(job_id):
    user, error = _require_recruitment_visibility()
    if error:
        return error
    obj = to_object_id(job_id)
    job = jobs_collection.find_one({"_id": obj}) if obj else None
    if not job:
        return fail("Job not found", 404)
    if not _is_job_viewer(user, job) and not role_permissions(user_role(user)).get("is_super_user"):
        return warn("Warning: this job is not shared with your account.")
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
    doc = {
        "title": title,
        "department": (data.get("department") or "Recruitment").strip(),
        "location": (data.get("location") or "Hybrid").strip(),
        "employment_type": data.get("employment_type") or "Full-time",
        "description": description,
        "keywords": keywords,
        "minimum_score": _safe_float(data.get("minimum_score"), 70),
        "status": data.get("status") or "Open",
        "created_by": user["_id"],
        "viewer_user_ids": _oid_list(data.get("viewer_user_ids") or data.get("viewers") or []),
        "controller_user_ids": _oid_list(data.get("controller_user_ids") or data.get("controllers") or []),
        "recruitment_progress_note": data.get("progress_note") or "JD created and ready for applicant screening",
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
    if not obj:
        return fail("Invalid job id")
    job = jobs_collection.find_one({"_id": obj})
    if not job:
        return fail("Job not found", 404)
    if not _is_job_controller(user, job):
        return warn("Warning: only the job creator, selected controllers, or Super User can update this job.")
    data = request.get_json() or {}
    allowed = ["title", "department", "location", "employment_type", "description", "keywords", "minimum_score", "status", "progress_note"]
    updates = {k: data[k] for k in allowed if k in data}
    if "viewer_user_ids" in data or "viewers" in data:
        updates["viewer_user_ids"] = _oid_list(data.get("viewer_user_ids") or data.get("viewers") or [])
    if "controller_user_ids" in data or "controllers" in data:
        updates["controller_user_ids"] = _oid_list(data.get("controller_user_ids") or data.get("controllers") or [])
    if "keywords" in updates:
        updates["keywords"] = _clean_csv_keywords(updates["keywords"])
    if "description" in updates and not updates.get("keywords"):
        updates["keywords"] = extract_keywords(updates["description"])
    if "minimum_score" in updates:
        updates["minimum_score"] = _safe_float(updates["minimum_score"], 70)
    updates["updated_at"] = now()
    jobs_collection.update_one({"_id": obj}, {"$set": updates})
    return ok("Job updated")


@recruitment_bp.post("/screen/single")
@jwt_required()
def screen_single_resume():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    form = request.form
    job_id = to_object_id(form.get("job_id"))
    job = jobs_collection.find_one({"_id": job_id}) if job_id else None
    if not job:
        return fail("Select a valid job before screening a resume")
    if not _is_job_controller(user, job):
        return warn("Warning: only the job creator, selected controllers, or Super User can screen resumes for this job.")
    try:
        safe, stored_path = _upload_resume(request.files.get("resume"))
    except ValueError as exc:
        return fail(str(exc))
    name = (form.get("candidate_name") or Path(safe).stem.replace("_", " ")).strip()
    email = (form.get("candidate_email") or "").strip().lower()
    resume_text = extract_resume_text(stored_path)
    app_doc, result = _screen_and_store_application(
        job,
        {
            "candidate_name": name,
            "candidate_email": email,
            "phone": form.get("phone") or "",
            "cover_note": form.get("cover_note") or "",
        },
        resume_text,
        safe,
        stored_path,
        source="Internal Single Screening",
        created_by=user["_id"],
    )
    return ok("Single resume screened", {"application": serialize_application(app_doc, user=user), "report": _serialize_report(result)}, 201)


@recruitment_bp.post("/screen/bulk")
@jwt_required()
def screen_bulk_resumes():
    user = current_user()
    if not user:
        return fail("User not found", 404)
    form = request.form
    job_id = to_object_id(form.get("job_id"))
    job = jobs_collection.find_one({"_id": job_id}) if job_id else None
    if not job:
        return fail("Select a valid job before bulk screening")
    if not _is_job_controller(user, job):
        return warn("Warning: only the job creator, selected controllers, or Super User can run bulk screening for this job.")
    files = request.files.getlist("resumes") or request.files.getlist("resume")
    if not files:
        return fail("Upload at least one resume file")
    created = []
    errors = []
    for file in files[:50]:
        try:
            safe, stored_path = _upload_resume(file)
            resume_text = extract_resume_text(stored_path)
            candidate_name = Path(safe).stem.replace("_", " ").replace("-", " ").strip() or "Unknown Candidate"
            app_doc, result = _screen_and_store_application(
                job,
                {"candidate_name": candidate_name, "candidate_email": "", "phone": "", "cover_note": ""},
                resume_text,
                safe,
                stored_path,
                source="Internal Bulk Screening",
                created_by=user["_id"],
            )
            created.append({"application": serialize_application(app_doc, user=user), "report": _serialize_report(result)})
        except Exception as exc:
            errors.append({"filename": getattr(file, "filename", "unknown"), "error": str(exc)})
    return ok("Bulk screening completed", {
        "job": serialize_job(job, include_counts=True),
        "processed": len(created),
        "failed": len(errors),
        "results": created,
        "errors": errors,
    }, 201)


def _serialize_report(report):
    return {
        "semantic_score": report.get("semantic_score"),
        "keyword_score": report.get("keyword_score"),
        "writing_score": report.get("writing_score"),
        "structure_score": report.get("structure_score"),
        "final_score": report.get("final_score"),
        "minimum_score": report.get("minimum_score"),
        "recommendation": report.get("recommendation"),
        "confidence": report.get("confidence"),
        "matched_keywords": report.get("matched_keywords", []),
        "missing_keywords": report.get("missing_keywords", []),
        "matched_keyword_details": report.get("matched_keyword_details", []),
        "highlighted_snippets": report.get("highlighted_snippets", []),
        "score_breakdown": report.get("score_breakdown", {}),
        "summary": report.get("summary"),
    }


@recruitment_bp.get("/applications")
@jwt_required()
def list_applications():
    user, error = _require_recruitment_visibility()
    if error:
        return error
    job_id = to_object_id(request.args.get("job_id"))
    accessible_job_ids = _job_ids_user_can_see(user)
    if job_id:
        if job_id not in accessible_job_ids and not role_permissions(user_role(user)).get("is_super_user"):
            return warn("Warning: this job is not shared with your account.")
        query = {"job_id": job_id}
    else:
        query = {"job_id": {"$in": accessible_job_ids}} if not role_permissions(user_role(user)).get("is_super_user") else {}
    only_shortlisted = request.args.get("shortlisted") == "1"
    if only_shortlisted:
        query["status"] = {"$in": ["Shortlisted", "Interview Scheduled", "Selected"]}
    review_status = request.args.get("review_status")
    if review_status:
        query["review_status"] = review_status
    apps = list(applications_collection.find(query).sort([("final_score", -1), ("created_at", -1)]).limit(300))
    return ok("Applications fetched", {"applications": [serialize_application(a, user=user) for a in apps]})


@recruitment_bp.get("/applications/<application_id>/report")
@jwt_required()
def application_report(application_id):
    user, error = _require_recruitment_visibility()
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    if not _can_view_application(user, app):
        return warn("Warning: this application is not shared with your account.")
    report = resume_screening_collection.find_one({"application_id": app["_id"]}) or {}
    return ok("AI screening report fetched", {
        "application": serialize_application(app, user=user),
        "report": _serialize_report(report),
    })


@recruitment_bp.get("/applications/<application_id>/resume")
@jwt_required()
def application_resume(application_id):
    user, error = _require_recruitment_visibility()
    if error:
        return error
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    if not _can_view_application(user, app):
        return warn("Warning: this applicant resume is not shared with your account.")
    mode = request.args.get("mode", "text")
    if mode == "download" and app.get("resume_path"):
        path = Path(app.get("resume_path"))
        if path.exists():
            return send_file(path, as_attachment=True, download_name=app.get("resume_filename") or path.name)
    return ok("Applicant resume fetched", {
        "application": serialize_application(app, user=user),
        "resume_filename": app.get("resume_filename"),
        "resume_text": app.get("resume_text", ""),
    })


@recruitment_bp.patch("/applications/<application_id>/review")
@jwt_required()
def review_application(application_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    app_id = to_object_id(application_id)
    if not app_id:
        return fail("Invalid application id")
    app = applications_collection.find_one({"_id": app_id})
    if not app:
        return fail("Application not found", 404)
    if not _can_control_application(user, app):
        return warn("Warning: only the job creator, selected controllers, or Super User can review this applicant.")
    data = request.get_json() or {}
    decision = (data.get("decision") or "Needs Review").strip()
    allowed = {"Pending Review", "Needs Review", "Shortlisted", "Interview Scheduled", "Selected", "Rejected", "On Hold"}
    if decision not in allowed:
        return fail("Invalid review decision")
    updates = {
        "review_status": decision,
        "review_notes": (data.get("review_notes") or "").strip(),
        "reviewed_by": user["_id"],
        "reviewed_at": now(),
        "updated_at": now(),
    }
    if decision in {"Shortlisted", "Selected", "Rejected", "On Hold", "Interview Scheduled"}:
        updates["status"] = decision
    applications_collection.update_one({"_id": app_id}, {"$set": updates})
    app = applications_collection.find_one({"_id": app_id})
    return ok("Application review updated", {"application": serialize_application(app, user=user)})


@recruitment_bp.post("/applications/<application_id>/assign-interview")
@jwt_required()
def assign_interview(application_id):
    user = current_user()
    if not user:
        return fail("User not found", 404)
    app_id = to_object_id(application_id)
    app = applications_collection.find_one({"_id": app_id}) if app_id else None
    if not app:
        return fail("Application not found", 404)
    if not _can_control_application(user, app):
        return warn("Warning: only the job creator, selected controllers, or Super User can allot the next interview process.")
    data = request.get_json() or {}
    interviewer_id = to_object_id(data.get("interviewer_user_id")) or user["_id"]
    panel_ids = _oid_list(data.get("panel_user_ids") or [])
    room_code = secrets.token_urlsafe(7).replace("-", "A").replace("_", "B")
    session = {
        "application_id": app["_id"],
        "job_id": app.get("job_id"),
        "candidate_name": app.get("candidate_name"),
        "candidate_email": app.get("candidate_email"),
        "interviewer_user_id": interviewer_id,
        "panel_user_ids": panel_ids,
        "mode": data.get("mode") or "AI Voice + Human Panel",
        "status": "Scheduled",
        "room_code": room_code,
        "scheduled_at": data.get("scheduled_at"),
        "created_by": user["_id"],
        "created_at": now(),
        "updated_at": now(),
    }
    res = interview_sessions_collection.insert_one(session)
    interview_rooms_collection.insert_one({
        "room_code": room_code,
        "session_id": res.inserted_id,
        "created_by": user["_id"],
        "participants": [str(interviewer_id)] + [str(x) for x in panel_ids] + [app.get("candidate_email")],
        "status": "open",
        "created_at": now(),
    })
    applications_collection.update_one({"_id": app["_id"]}, {"$set": {"status": "Interview Scheduled", "review_status": "Interview Scheduled", "next_process": data.get("mode") or "AI Voice + Human Panel", "assigned_interviewer_user_id": interviewer_id, "panel_user_ids": panel_ids, "updated_at": now()}})
    return ok("Interview room created", {"session_id": str(res.inserted_id), "room_code": room_code, "join_url": f"/interview-room/{room_code}"}, 201)


@recruitment_bp.get("/interviews")
@jwt_required()
def list_interviews():
    user, error = require_perm("can_run_voice_interviews")
    if error:
        return error
    perms = role_permissions(user_role(user))
    query = {} if perms.get("can_manage_recruitment") or perms.get("can_view_company_dashboard") else {"interviewer_user_id": user["_id"]}
    rows = list(interview_sessions_collection.find(query).sort("created_at", -1).limit(100))
    return ok("Interviews fetched", {"interviews": [{
        "id": str(r["_id"]), "candidate_name": r.get("candidate_name"), "candidate_email": r.get("candidate_email"),
        "mode": r.get("mode"), "status": r.get("status"), "room_code": r.get("room_code"), "scheduled_at": r.get("scheduled_at")
    } for r in rows]})


@recruitment_bp.post("/ai/voice-answer")
@jwt_required(optional=True)
def voice_answer_eval():
    data = request.get_json() or {}
    result = evaluate_answer(
        data.get("question") or "Tell me about your relevant experience.",
        data.get("expected_answer") or data.get("rubric") or data.get("job_context") or "",
        data.get("candidate_answer") or data.get("transcript") or "",
        data.get("keywords"),
    )
    return ok("Voice transcript evaluated", {"evaluation": result})


@recruitment_bp.get("/rooms/<room_code>/messages")
@jwt_required(optional=True)
def room_messages(room_code):
    room = interview_rooms_collection.find_one({"room_code": room_code})
    if not room:
        return fail("Interview room not found", 404)
    rows = list(interview_messages_collection.find({"room_code": room_code}).sort("created_at", 1).limit(200))
    return ok("Room messages fetched", {"messages": [{
        "sender": r.get("sender"), "message": r.get("message"), "kind": r.get("kind", "chat"),
        "created_at": _serialize_dt(r.get("created_at"))
    } for r in rows]})


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
