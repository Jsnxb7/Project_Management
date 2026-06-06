import copy
import os
import re
from pathlib import Path
from threading import RLock

from bson import ObjectId
from bson.json_util import dumps, loads
from pymongo import MongoClient, ReplaceOne, ASCENDING, DESCENDING
from config import Config


COLLECTION_REGISTRY = {
    # Core users and people
    "users": "users.json",
    "employees": "employees.json",
    "employee_documents": "employee_documents.json",

    # Attendance and leave
    "attendance": "attendance.json",
    "hrms_attendance_rules": "hrms_attendance_rules.json",
    "hrms_attendance_corrections": "hrms_attendance_corrections.json",
    "hrms_attendance_meetings": "hrms_attendance_meetings.json",
    "hrms_attendance_reviews": "hrms_attendance_reviews.json",
    "hrms_leave_requests": "hrms_leave_requests.json",
    "hrms_manager_assignments": "hrms_manager_assignments.json",
    "leave_requests": "leave_requests.json",  # legacy-compatible leave API source

    # Simplified payroll + performance
    "hrms_payroll_profiles": "hrms_payroll_profiles.json",
    "hrms_payroll_cycles": "hrms_payroll_cycles.json",
    "hrms_payroll_items": "hrms_payroll_items.json",
    "hrms_payroll_adjustments": "hrms_payroll_adjustments.json",
    "hrms_payouts": "hrms_payouts.json",
    "hrms_payroll_queries": "hrms_payroll_queries.json",
    "hrms_performance_templates": "hrms_performance_templates.json",
    "hrms_performance_goals": "hrms_performance_goals.json",
    "hrms_performance_checklists": "hrms_performance_checklists.json",
    "hrms_performance_scores": "hrms_performance_scores.json",

    # Recruitment
    "jobs": "jobs.json",
    "job_knowledge_base": "job_knowledge_base.json",
    "applications": "applications.json",
    "resume_screening_results": "resume_screening_results.json",
    "recruitment_candidates": "recruitment_candidates.json",
    "interview_sessions": "interview_sessions.json",
    "interview_messages": "interview_messages.json",
    "interview_rooms": "interview_rooms.json",
    "candidate_processes": "candidate_processes.json",

    # Communication/system
    "hrms_messages": "hrms_messages.json",
    "notifications": "notifications.json",
    "activity_logs": "activity_logs.json",
    "login_sessions": "login_sessions.json",
    "hrms_audit_logs": "hrms_audit_logs.json",

    # HR support and UI/theme
    "hr_cases": "hr_cases.json",
    "learning_records": "learning_records.json",
    "user_themes": "user_themes.json",
    "hrms_ui_settings": "hrms_ui_settings.json",
    "hrms_ui_page_groups": "hrms_ui_page_groups.json",
}

DEPRECATED_COLLECTION_NAMES = [
    "payroll",
    "performance_reviews",
    "hrms_performance_cycles",
    "hrms_performance_milestones",
    "hrms_performance_feedback",
]

COLLECTION_NAMES = list(COLLECTION_REGISTRY.keys())


JSON_DB_DIR = Path(os.getenv("JSON_DB_DIR", Path(__file__).resolve().parent / "json_data"))
_LOCK = RLock()

if not Config.MONGO_URI:
    raise RuntimeError("MONGO_URI is missing. Create a .env file using .env.example.")

client = MongoClient(
    Config.MONGO_URI,
    maxPoolSize=200,
    minPoolSize=5,
    serverSelectionTimeoutMS=20000,
    connectTimeoutMS=20000,
    retryWrites=True,
)
db = client[Config.DB_NAME]


class InsertOneResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class UpdateResult:
    def __init__(self, matched_count, modified_count, upserted_id=None):
        self.matched_count = matched_count
        self.modified_count = modified_count
        self.upserted_id = upserted_id


class DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class JsonCursor:
    def __init__(self, rows):
        self.rows = rows
        self._index = 0

    def sort(self, key_or_list, direction=None):
        sort_keys = key_or_list if isinstance(key_or_list, list) else [(key_or_list, direction or ASCENDING)]
        for key, order in reversed(sort_keys):
            self.rows.sort(key=lambda row: _sort_value(_get_value(row, key)), reverse=order == DESCENDING or order == -1)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        self._index = 0
        return self

    def __iter__(self):
        self._index = 0
        return self

    def __next__(self):
        if self._index >= len(self.rows):
            raise StopIteration
        row = self.rows[self._index]
        self._index += 1
        return row


class JsonCollection:
    def __init__(self, name):
        self.name = name
        self.path = JSON_DB_DIR / COLLECTION_REGISTRY.get(name, f"{name}.json")

    def _read(self):
        JSON_DB_DIR.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")
            return []
        raw = self.path.read_text(encoding="utf-8").strip()
        return loads(raw) if raw else []

    def _write(self, rows):
        JSON_DB_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(dumps(rows, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    def find_one(self, query=None, projection=None):
        with _LOCK:
            for row in self._read():
                if _matches(row, query or {}):
                    return _project(copy.deepcopy(row), projection)
        return None

    def find(self, query=None, projection=None):
        with _LOCK:
            rows = [
                _project(copy.deepcopy(row), projection)
                for row in self._read()
                if _matches(row, query or {})
            ]
        return JsonCursor(rows)

    def count_documents(self, query=None, *args, **kwargs):
        with _LOCK:
            count = sum(1 for row in self._read() if _matches(row, query or {}))
        limit = kwargs.get("limit")
        return min(count, limit) if limit else count

    def _mongo_collection(self):
        return db[self.name]

    def _mirror_replace_one(self, document):
        if os.getenv("DISABLE_MONGO_MIRROR", "0") == "1":
            return
        try:
            self._mongo_collection().replace_one({"_id": document.get("_id")}, copy.deepcopy(document), upsert=True)
        except Exception:
            # JSON remains the reliable local fallback; mirror failures should not break app writes.
            pass

    def _mirror_update_many(self, query, update):
        if os.getenv("DISABLE_MONGO_MIRROR", "0") == "1":
            return
        try:
            self._mongo_collection().update_many(copy.deepcopy(query or {}), copy.deepcopy(update))
        except Exception:
            pass

    def _mirror_delete_many(self, query):
        if os.getenv("DISABLE_MONGO_MIRROR", "0") == "1":
            return
        try:
            self._mongo_collection().delete_many(copy.deepcopy(query or {}))
        except Exception:
            pass

    def insert_one(self, document):
        with _LOCK:
            rows = self._read()
            doc = copy.deepcopy(document)
            doc.setdefault("_id", ObjectId())
            rows.append(doc)
            self._write(rows)
        self._mirror_replace_one(doc)
        return InsertOneResult(doc["_id"])

    def update_one(self, query, update, upsert=False):
        return self._update(query, update, upsert=upsert, multi=False)

    def update_many(self, query, update, upsert=False):
        return self._update(query, update, upsert=upsert, multi=True)

    def _update(self, query, update, upsert=False, multi=False):
        with _LOCK:
            rows = self._read()
            matched = 0
            modified = 0
            for row in rows:
                if not _matches(row, query or {}):
                    continue
                before = copy.deepcopy(row)
                _apply_update(row, update, is_insert=False)
                matched += 1
                modified += int(row != before)
                if not multi:
                    break

            upserted_id = None
            if matched == 0 and upsert:
                doc = _document_from_query(query or {})
                _apply_update(doc, update, is_insert=True)
                doc.setdefault("_id", ObjectId())
                rows.append(doc)
                matched = 1
                modified = 1
                upserted_id = doc["_id"]

            if modified:
                self._write(rows)
                # Mirror the exact JSON result back to Mongo so JSON and Atlas stay aligned.
                try:
                    for row in rows:
                        if _matches(row, query or {}):
                            self._mirror_replace_one(row)
                            if not multi:
                                break
                except Exception:
                    self._mirror_update_many(query or {}, update)
        return UpdateResult(matched, modified, upserted_id)

    def delete_one(self, query):
        with _LOCK:
            rows = self._read()
            kept = []
            deleted = 0
            for row in rows:
                if deleted == 0 and _matches(row, query or {}):
                    deleted = 1
                    continue
                kept.append(row)
            if deleted:
                self._write(kept)
                self._mirror_delete_many(query or {})
        return DeleteResult(deleted)

    def delete_many(self, query):
        with _LOCK:
            rows = self._read()
            kept = [row for row in rows if not _matches(row, query or {})]
            deleted = len(rows) - len(kept)
            if deleted:
                self._write(kept)
                self._mirror_delete_many(query or {})
        return DeleteResult(deleted)

    def aggregate(self, pipeline):
        rows = list(self.find({}))
        for stage in pipeline:
            if "$match" in stage:
                rows = [row for row in rows if _matches(row, stage["$match"])]
            elif "$limit" in stage:
                rows = rows[: stage["$limit"]]
            elif "$group" in stage:
                rows = _group_rows(rows, stage["$group"])
        return JsonCursor(rows)

    def index_information(self):
        return {}

    def create_index(self, *args, **kwargs):
        return kwargs.get("name")

    def drop_index(self, *args, **kwargs):
        return None


def _sort_value(value):
    if value is None:
        return (0, "")
    return (1, str(value).lower() if isinstance(value, str) else value)


def _get_value(document, dotted_key):
    value = document
    for part in dotted_key.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _set_value(document, dotted_key, value):
    target = document
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _unset_value(document, dotted_key):
    target = document
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        target = target.get(part)
        if not isinstance(target, dict):
            return
    target.pop(parts[-1], None)


def _matches(document, query):
    for key, expected in (query or {}).items():
        if key == "$and":
            if not all(_matches(document, item) for item in expected):
                return False
            continue
        if key == "$or":
            if not any(_matches(document, item) for item in expected):
                return False
            continue

        actual = _get_value(document, key)
        if isinstance(expected, dict) and any(k.startswith("$") for k in expected):
            if not _operator_match(actual, expected):
                return False
        elif not _value_equal(actual, expected):
            return False
    return True


def _operator_match(actual, operators):
    for op, expected in operators.items():
        if op == "$options":
            continue
        if op == "$ne" and _value_equal(actual, expected):
            return False
        if op == "$in" and not _in_values(actual, expected):
            return False
        if op == "$nin" and _in_values(actual, expected):
            return False
        if op == "$all" and not all(item in (actual or []) for item in expected):
            return False
        if op == "$exists" and ((_present(actual)) != bool(expected)):
            return False
        if op == "$gte" and not (_present(actual) and actual >= expected):
            return False
        if op == "$lte" and not (_present(actual) and actual <= expected):
            return False
        if op == "$gt" and not (_present(actual) and actual > expected):
            return False
        if op == "$lt" and not (_present(actual) and actual < expected):
            return False
        if op == "$regex":
            flags = re.I if operators.get("$options") == "i" else 0
            if not re.search(expected, str(actual or ""), flags):
                return False
    return True


def _present(value):
    return value is not None


def _value_equal(actual, expected):
    if isinstance(actual, list):
        return expected in actual
    return actual == expected


def _in_values(actual, expected_values):
    if isinstance(actual, list):
        return any(item in expected_values for item in actual)
    return actual in expected_values


def _project(document, projection):
    if not projection:
        return document
    include_keys = {key for key, value in projection.items() if value}
    exclude_keys = {key for key, value in projection.items() if not value}
    if include_keys:
        projected = {}
        if projection.get("_id", 1) and "_id" in document:
            projected["_id"] = document["_id"]
        for key in include_keys:
            if key in document:
                projected[key] = document[key]
        return projected
    for key in exclude_keys:
        document.pop(key, None)
    return document


def _apply_update(document, update, is_insert=False):
    if not any(key.startswith("$") for key in update):
        document.clear()
        document.update(copy.deepcopy(update))
        return

    for key, value in update.get("$set", {}).items():
        _set_value(document, key, copy.deepcopy(value))
    if is_insert:
        for key, value in update.get("$setOnInsert", {}).items():
            _set_value(document, key, copy.deepcopy(value))
    for key, value in update.get("$inc", {}).items():
        _set_value(document, key, (_get_value(document, key) or 0) + value)
    for key, value in update.get("$unset", {}).items():
        _unset_value(document, key)
    for key, value in update.get("$push", {}).items():
        target = _get_value(document, key) or []
        values = value.get("$each", []) if isinstance(value, dict) and "$each" in value else [value]
        target.extend(copy.deepcopy(values))
        _set_value(document, key, target)
    for key, value in update.get("$addToSet", {}).items():
        target = _get_value(document, key) or []
        values = value.get("$each", []) if isinstance(value, dict) and "$each" in value else [value]
        for item in values:
            if item not in target:
                target.append(copy.deepcopy(item))
        _set_value(document, key, target)
    for key, value in update.get("$pull", {}).items():
        target = _get_value(document, key) or []
        if isinstance(target, list):
            _set_value(document, key, [item for item in target if item != value])


def _document_from_query(query):
    doc = {}
    for key, value in query.items():
        if key.startswith("$"):
            continue
        if isinstance(value, dict) and any(k.startswith("$") for k in value):
            continue
        _set_value(doc, key, copy.deepcopy(value))
    return doc


def _group_rows(rows, spec):
    group_key = spec.get("_id")
    grouped = {}
    for row in rows:
        key = _get_value(row, group_key[1:]) if isinstance(group_key, str) and group_key.startswith("$") else group_key
        bucket = grouped.setdefault(key, {"_id": key})
        for output_key, expression in spec.items():
            if output_key == "_id":
                continue
            if isinstance(expression, dict) and "$sum" in expression:
                bucket[output_key] = bucket.get(output_key, 0) + expression["$sum"]
    return list(grouped.values())


def copy_mongo_to_json(collection_names=None):
    names = collection_names or COLLECTION_NAMES
    JSON_DB_DIR.mkdir(parents=True, exist_ok=True)
    copied = {}
    for name in names:
        rows = list(db[name].find({}))
        (JSON_DB_DIR / f"{name}.json").write_text(dumps(rows, indent=2), encoding="utf-8")
        copied[name] = len(rows)
    return copied


def sync_json_to_mongo(collection_names=None):
    names = collection_names or COLLECTION_NAMES
    synced = {}
    for name in names:
        path = JSON_DB_DIR / f"{name}.json"
        if not path.exists():
            continue
        try:
            rows = loads(path.read_text(encoding="utf-8") or "[]")
            if not isinstance(rows, list):
                synced[name] = "skipped_non_array"
                continue

            changed = False
            valid_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    changed = True
                    continue
                if not row.get("_id"):
                    row["_id"] = ObjectId()
                    changed = True
                valid_rows.append(row)

            if changed:
                path.write_text(dumps(valid_rows, indent=2), encoding="utf-8")

            mongo_collection = db[name]
            if valid_rows:
                mongo_collection.bulk_write([ReplaceOne({"_id": row["_id"]}, row, upsert=True) for row in valid_rows])
            synced[name] = len(valid_rows)
        except Exception as exc:
            raise RuntimeError(f"{name}: {exc}") from exc
    return synced


def mirror_json_to_mongo(collection_names=None):
    """Non-destructive JSON -> Mongo Atlas mirror used on startup and for repair.

    Unlike sync_json_to_mongo(), this never deletes Atlas-only rows. It only upserts
    JSON mirror rows, which is safer for deployed Atlas databases.
    """
    names = collection_names or COLLECTION_NAMES
    mirrored = {}
    if os.getenv("DISABLE_MONGO_MIRROR", "0") == "1":
        return mirrored
    for name in names:
        path = JSON_DB_DIR / f"{name}.json"
        if not path.exists():
            continue
        try:
            rows = loads(path.read_text(encoding="utf-8") or "[]")
            if not isinstance(rows, list):
                mirrored[name] = "skipped_non_array"
                continue
            changed = False
            valid_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    changed = True
                    continue
                if not row.get("_id"):
                    row["_id"] = ObjectId()
                    changed = True
                valid_rows.append(row)
            if changed:
                path.write_text(dumps(valid_rows, indent=2), encoding="utf-8")
            if valid_rows:
                db[name].bulk_write([ReplaceOne({"_id": row["_id"]}, row, upsert=True) for row in valid_rows])
            mirrored[name] = len(valid_rows)
        except Exception as exc:
            mirrored[name] = f"mirror_failed: {exc}"
    return mirrored


def sync_mongo_to_json(collection_names=None):
    """Safely mirrors Atlas rows into local JSON without deleting JSON-only rows.

    Conflict rule: newest updated_at wins when both sides contain the same _id.
    If timestamps are missing, the existing JSON row is preserved.
    """
    names = collection_names or COLLECTION_NAMES
    JSON_DB_DIR.mkdir(parents=True, exist_ok=True)
    synced = {}
    for name in names:
        path = JSON_DB_DIR / COLLECTION_REGISTRY.get(name, f"{name}.json")
        try:
            local_rows = loads(path.read_text(encoding="utf-8") or "[]") if path.exists() else []
            if not isinstance(local_rows, list):
                local_rows = []
            local_by_id = {str(row.get("_id")): row for row in local_rows if isinstance(row, dict) and row.get("_id")}
            for remote in db[name].find({}):
                key = str(remote.get("_id"))
                local = local_by_id.get(key)
                if not local:
                    local_by_id[key] = remote
                    continue
                remote_updated = remote.get("updated_at") or remote.get("created_at")
                local_updated = local.get("updated_at") or local.get("created_at")
                if remote_updated and local_updated and remote_updated > local_updated:
                    local_by_id[key] = remote
            rows = list(local_by_id.values())
            path.write_text(dumps(rows, indent=2), encoding="utf-8")
            synced[name] = len(rows)
        except Exception as exc:
            synced[name] = f"sync_failed: {exc}"
    return synced


def ensure_json_database():
    JSON_DB_DIR.mkdir(parents=True, exist_ok=True)
    created = []
    for name in COLLECTION_NAMES:
        path = JSON_DB_DIR / f"{name}.json"
        if not path.exists():
            path.write_text("[]", encoding="utf-8")
            created.append(name)
    return created


def has_duplicate_values(collection, field):
    duplicates = list(collection.aggregate([
        {"$match": {field: {"$type": "string", "$ne": ""}}},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 1},
    ]))
    return bool(duplicates)


def ensure_index(collection, keys, **options):
    return None


def ensure_performance_indexes():
    ensure_json_database()
    # Keep the JSON fallback and Mongo Atlas mirror aligned at startup.
    mirror_json_to_mongo()


users_collection = JsonCollection("users")
notifications_collection = JsonCollection("notifications")
activity_logs_collection = JsonCollection("activity_logs")
login_sessions_collection = JsonCollection("login_sessions")
employees_collection = JsonCollection("employees")
attendance_collection = JsonCollection("attendance")
payroll_collection = JsonCollection("payroll")
performance_reviews_collection = JsonCollection("performance_reviews")
leave_requests_collection = JsonCollection("leave_requests")
recruitment_candidates_collection = JsonCollection("recruitment_candidates")
employee_documents_collection = JsonCollection("employee_documents")
hr_cases_collection = JsonCollection("hr_cases")
learning_records_collection = JsonCollection("learning_records")
jobs_collection = JsonCollection("jobs")
job_knowledge_collection = JsonCollection("job_knowledge_base")
applications_collection = JsonCollection("applications")
resume_screening_collection = JsonCollection("resume_screening_results")
interview_sessions_collection = JsonCollection("interview_sessions")
interview_messages_collection = JsonCollection("interview_messages")
interview_rooms_collection = JsonCollection("interview_rooms")
user_theme_collection = JsonCollection("user_themes")
hrms_messages_collection = JsonCollection("hrms_messages")
hrms_attendance_rules_collection = JsonCollection("hrms_attendance_rules")
hrms_manager_assignments_collection = JsonCollection("hrms_manager_assignments")
hrms_attendance_reviews_collection = JsonCollection("hrms_attendance_reviews")
hrms_attendance_meetings_collection = JsonCollection("hrms_attendance_meetings")
hrms_attendance_corrections_collection = JsonCollection("hrms_attendance_corrections")
hrms_audit_logs_collection = JsonCollection("hrms_audit_logs")

hrms_payroll_profiles_collection = JsonCollection("hrms_payroll_profiles")
hrms_payroll_cycles_collection = JsonCollection("hrms_payroll_cycles")
hrms_payroll_items_collection = JsonCollection("hrms_payroll_items")
hrms_payroll_adjustments_collection = JsonCollection("hrms_payroll_adjustments")
hrms_payouts_collection = JsonCollection("hrms_payouts")
hrms_payroll_queries_collection = JsonCollection("hrms_payroll_queries")
hrms_performance_cycles_collection = JsonCollection("hrms_performance_cycles")
hrms_performance_templates_collection = JsonCollection("hrms_performance_templates")
hrms_performance_goals_collection = JsonCollection("hrms_performance_goals")
hrms_performance_milestones_collection = JsonCollection("hrms_performance_milestones")
hrms_performance_checklists_collection = JsonCollection("hrms_performance_checklists")
hrms_performance_scores_collection = JsonCollection("hrms_performance_scores")
hrms_performance_feedback_collection = JsonCollection("hrms_performance_feedback")

ensure_performance_indexes()
