from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import user_theme_collection
from services.hrms_service import to_object_id
from utils.response import ok, fail

theme_bp = Blueprint("theme_bp", __name__)

THEME_KITS = [
    {
        "kit_id": "neo_mint",
        "name": "Neo Mint",
        "description": "Default AI-HRMS glass theme with mint and blue accents.",
        "primary": "#78e0c2",
        "secondary": "#8fb7ff",
        "background": "#080b12",
        "surface": "rgba(18, 24, 34, 0.78)",
        "surface2": "rgba(28, 38, 52, 0.82)",
        "text": "#f8fbff",
        "text2": "#d7e2ef",
        "muted": "#91a4b8",
        "sidebar": "rgba(8, 11, 18, 0.84)",
        "radius": "8px",
        "density": "comfortable",
        "video_opacity": "0.12",
    },
    {
        "kit_id": "executive_dark",
        "name": "Executive Dark",
        "description": "Sharper enterprise look for admins and leadership dashboards.",
        "primary": "#f2c66d",
        "secondary": "#7aa2ff",
        "background": "#06080d",
        "surface": "rgba(15, 18, 28, 0.86)",
        "surface2": "rgba(26, 30, 44, 0.9)",
        "text": "#fffaf0",
        "text2": "#e9dfcc",
        "muted": "#a99f90",
        "sidebar": "rgba(5, 7, 12, 0.9)",
        "radius": "10px",
        "density": "comfortable",
        "video_opacity": "0.08",
    },
    {
        "kit_id": "recruiter_pulse",
        "name": "Recruiter Pulse",
        "description": "Bright recruitment workspace for resumes, interviews, and candidates.",
        "primary": "#ff7ccf",
        "secondary": "#8ad8ff",
        "background": "#100817",
        "surface": "rgba(31, 18, 42, 0.82)",
        "surface2": "rgba(45, 25, 58, 0.88)",
        "text": "#fff7ff",
        "text2": "#f1d8ef",
        "muted": "#b996b5",
        "sidebar": "rgba(18, 8, 28, 0.88)",
        "radius": "18px",
        "density": "comfortable",
        "video_opacity": "0.14",
    },
    {
        "kit_id": "payroll_focus",
        "name": "Payroll Focus",
        "description": "Clean finance-oriented theme for payroll and compliance work.",
        "primary": "#9df28f",
        "secondary": "#55d6be",
        "background": "#07110c",
        "surface": "rgba(14, 31, 23, 0.84)",
        "surface2": "rgba(22, 45, 34, 0.88)",
        "text": "#f3fff5",
        "text2": "#d3ecd8",
        "muted": "#91b49a",
        "sidebar": "rgba(6, 17, 12, 0.9)",
        "radius": "12px",
        "density": "compact",
        "video_opacity": "0.07",
    },
    {
        "kit_id": "cloud_light",
        "name": "Cloud Light",
        "description": "Readable light kit for daily employee self-service screens.",
        "primary": "#2563eb",
        "secondary": "#14b8a6",
        "background": "#eaf1fb",
        "surface": "rgba(255, 255, 255, 0.82)",
        "surface2": "rgba(255, 255, 255, 0.92)",
        "text": "#101827",
        "text2": "#253247",
        "muted": "#64748b",
        "sidebar": "rgba(247, 250, 255, 0.9)",
        "radius": "16px",
        "density": "comfortable",
        "video_opacity": "0.03",
    },
    {
        "kit_id": "midnight_compact",
        "name": "Midnight Compact",
        "description": "Dense operations kit for high-volume HR teams and 5,000+ employee lists.",
        "primary": "#a78bfa",
        "secondary": "#22d3ee",
        "background": "#070714",
        "surface": "rgba(16, 16, 34, 0.86)",
        "surface2": "rgba(28, 28, 52, 0.9)",
        "text": "#f7f5ff",
        "text2": "#dad5ff",
        "muted": "#9c96bd",
        "sidebar": "rgba(8, 8, 24, 0.92)",
        "radius": "6px",
        "density": "compact",
        "video_opacity": "0.1",
    },
]

DEFAULT_THEME = THEME_KITS[0].copy()

ALLOWED = [
    "kit_id", "name", "description", "primary", "secondary", "background", "surface", "surface2",
    "text", "text2", "muted", "sidebar", "radius", "density", "video_opacity",
]


def serialize(theme):
    if not theme:
        return DEFAULT_THEME
    data = DEFAULT_THEME.copy()
    data.update(theme.get("theme", {}))
    return data


@theme_bp.get("/kits")
def theme_kits():
    return ok("Theme kits fetched", {"kits": THEME_KITS})


@theme_bp.get("/me")
@jwt_required()
def my_theme():
    user_id = to_object_id(get_jwt_identity())
    theme = user_theme_collection.find_one({"user_id": user_id})
    return ok("Theme fetched", {"theme": serialize(theme), "kits": THEME_KITS})


@theme_bp.put("/me")
@jwt_required()
def save_theme():
    user_id = to_object_id(get_jwt_identity())
    data = request.get_json() or {}
    theme = {k: data[k] for k in ALLOWED if k in data}
    if not theme:
        return fail("No theme values provided")
    now = datetime.now(timezone.utc)
    user_theme_collection.update_one(
        {"user_id": user_id},
        {"$set": {"theme": theme, "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return ok("Theme saved", {"theme": serialize({"theme": theme})})
