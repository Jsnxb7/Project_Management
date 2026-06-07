from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from bson import ObjectId
from flask import jsonify


# Flask's jsonify cannot serialize Mongo ObjectId/datetime values directly.
# Since the app is now local-Mongo-only, every API response should pass through
# this sanitizer before jsonify. This keeps routes simple and prevents 500s from
# documents returned by PyMongo.
def mongo_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, tuple):
        return [mongo_safe(v) for v in value]
    if isinstance(value, list):
        return [mongo_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): mongo_safe(v) for k, v in value.items()}
    return value


def ok(message="Success", data=None, status=200):
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = mongo_safe(data)
    return jsonify(payload), status


def fail(message="Something went wrong", status=400, data=None):
    payload = {"success": False, "message": message}
    if data is not None:
        payload["data"] = mongo_safe(data)
    return jsonify(payload), status


def warn(message="Please review this before continuing", data=None, status=200):
    payload = {"success": False, "warning": True, "message": message}
    if data is not None:
        payload["data"] = mongo_safe(data)
    return jsonify(payload), status
