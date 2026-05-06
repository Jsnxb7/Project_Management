from functools import wraps
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from utils.response import fail


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        return fn(*args, **kwargs)
    return wrapper


def current_user_id():
    return get_jwt_identity()

# Extra route-level decorators can be added here later.
