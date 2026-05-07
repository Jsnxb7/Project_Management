from flask import jsonify


def ok(message="Success", data=None, status=200):
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def fail(message="Something went wrong", status=400):
    return jsonify({"success": False, "message": message}), status


def warn(message="Please review this before continuing", data=None, status=200):
    payload = {"success": False, "warning": True, "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status
