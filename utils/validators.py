import re


def valid_email(email):
    if not email:
        return False
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, email) is not None


def valid_password(password):
    if not password or len(password) < 8:
        return False
    has_letter = any(ch.isalpha() for ch in password)
    has_number = any(ch.isdigit() for ch in password)
    return has_letter and has_number
