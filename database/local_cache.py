from __future__ import annotations

"""Small local read-through cache for Mongo collections.

The cache is intentionally conservative: unsupported query shapes fall back to
MongoDB, while common HRMS list/detail queries read from local JSON after the
startup warmup completes.
"""

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from bson import ObjectId, json_util


CACHE_DIR = Path(os.getenv("MONGO_LOCAL_CACHE_DIR", "database/local_cache"))
CACHE_ENABLED = os.getenv("MONGO_LOCAL_CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
_cache: dict[str, list[dict[str, Any]]] = {}
_ready: set[str] = set()
_lock = threading.RLock()
_warming = False
_last_error: str | None = None


def _path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def _load_file(name: str) -> list[dict[str, Any]]:
    path = _path(name)
    if not path.exists():
        return []
    return json_util.loads(path.read_text(encoding="utf-8"))


def _save_file(name: str, rows: list[dict[str, Any]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(json_util.dumps(rows), encoding="utf-8")


def _projection_from_args(args, kwargs) -> tuple[dict[str, Any] | None, tuple, dict]:
    args = tuple(args or ())
    kwargs = dict(kwargs or {})
    projection = kwargs.pop("projection", None)
    if args:
        projection = args[0]
        args = args[1:]
    return projection, args, kwargs


def _apply_projection(row: dict[str, Any], projection: dict[str, Any] | None) -> dict[str, Any]:
    if not projection:
        return row
    include_keys = {key for key, value in projection.items() if value}
    exclude_keys = {key for key, value in projection.items() if not value}
    if include_keys:
        projected = {key: row.get(key) for key in include_keys if key in row}
        if projection.get("_id", 1) and "_id" in row:
            projected["_id"] = row["_id"]
        return projected
    return {key: value for key, value in row.items() if key not in exclude_keys}


def _coerce(value: Any) -> Any:
    if isinstance(value, dict) and "$oid" in value:
        return ObjectId(value["$oid"])
    return value


def _nested(row: dict[str, Any], key: str) -> Any:
    value: Any = row
    for part in key.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _equals(left: Any, right: Any) -> bool:
    right = _coerce(right)
    if isinstance(left, list):
        return any(_equals(item, right) for item in left)
    return left == right


def _compare(left: Any, right: Any, op: str) -> bool:
    right = _coerce(right)
    if isinstance(left, datetime) and isinstance(right, str):
        try:
            right = datetime.fromisoformat(right.replace("Z", "+00:00"))
        except Exception:
            pass
    if op == "$ne":
        return not _equals(left, right)
    if op == "$in":
        options = [_coerce(v) for v in (right or [])]
        if isinstance(left, list):
            return any(item in options for item in left)
        return left in options
    if op == "$nin":
        options = [_coerce(v) for v in (right or [])]
        if isinstance(left, list):
            return not any(item in options for item in left)
        return left not in options
    if op == "$exists":
        return (left is not None) is bool(right)
    if op == "$gte":
        return left is not None and left >= right
    if op == "$lte":
        return left is not None and left <= right
    if op == "$gt":
        return left is not None and left > right
    if op == "$lt":
        return left is not None and left < right
    if op == "$regex":
        import re
        flags = re.I
        if isinstance(left, list):
            return any(re.search(str(right), str(item or ""), flags) is not None for item in left)
        return re.search(str(right), str(left or ""), flags) is not None
    if op == "$type":
        if right == "string":
            return isinstance(left, str)
        if right == "array":
            return isinstance(left, list)
        if right == "object":
            return isinstance(left, dict)
        return True
    return False


def _matches(row: dict[str, Any], query: dict[str, Any] | None) -> bool:
    if not query:
        return True
    for key, expected in query.items():
        if key == "$and":
            if not all(_matches(row, part) for part in expected):
                return False
            continue
        if key == "$or":
            if not any(_matches(row, part) for part in expected):
                return False
            continue
        actual = _nested(row, key)
        if isinstance(expected, dict):
            for op, value in expected.items():
                if op == "$options":
                    continue
                if not _compare(actual, value, op):
                    return False
        elif not _equals(actual, expected):
            return False
    return True


class CachedCursor:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def sort(self, key_or_list, direction=None):
        keys = key_or_list if isinstance(key_or_list, list) else [(key_or_list, direction or 1)]
        for key, order in reversed(keys):
            self.rows.sort(key=lambda row: (str(_nested(row, key) is None), str(_nested(row, key) or "")), reverse=int(order or 1) < 0)
        return self

    def skip(self, value: int):
        self.rows = self.rows[int(value or 0):]
        return self

    def limit(self, value: int):
        if int(value or 0) > 0:
            self.rows = self.rows[:int(value)]
        return self

    def batch_size(self, _value: int):
        return self

    def close(self):
        return None

    def __iter__(self):
        return iter(self.rows)


class CachedCollection:
    def __init__(self, collection):
        self._collection = collection
        self.name = collection.name

    def __getattr__(self, name: str):
        return getattr(self._collection, name)

    def _rows(self) -> list[dict[str, Any]] | None:
        if not CACHE_ENABLED:
            return None
        with _lock:
            if self.name in _cache:
                return list(_cache[self.name])
            if _path(self.name).exists():
                _cache[self.name] = _load_file(self.name)
                _ready.add(self.name)
                return list(_cache[self.name])
        return None

    def find(self, query=None, *args, **kwargs):
        rows = self._rows()
        projection, rest_args, rest_kwargs = _projection_from_args(args, kwargs)
        if rows is None or rest_args or rest_kwargs:
            return self._collection.find(query or {}, *args, **kwargs)
        try:
            return CachedCursor([_apply_projection(row, projection) for row in rows if _matches(row, query or {})])
        except Exception:
            return self._collection.find(query or {}, *args, **kwargs)

    def find_one(self, query=None, *args, **kwargs):
        rows = self._rows()
        projection, rest_args, rest_kwargs = _projection_from_args(args, kwargs)
        if rows is None or rest_args or rest_kwargs:
            return self._collection.find_one(query or {}, *args, **kwargs)
        try:
            for row in rows:
                if _matches(row, query or {}):
                    return _apply_projection(row, projection)
            return None
        except Exception:
            return self._collection.find_one(query or {}, *args, **kwargs)

    def count_documents(self, query=None, *args, **kwargs):
        rows = self._rows()
        if rows is None or args or kwargs:
            return self._collection.count_documents(query or {}, *args, **kwargs)
        try:
            return sum(1 for row in rows if _matches(row, query or {}))
        except Exception:
            return self._collection.count_documents(query or {}, *args, **kwargs)

    def _write_refresh(self, result):
        refresh_collection_async(self.name, self._collection)
        return result

    def insert_one(self, *args, **kwargs): return self._write_refresh(self._collection.insert_one(*args, **kwargs))
    def insert_many(self, *args, **kwargs): return self._write_refresh(self._collection.insert_many(*args, **kwargs))
    def update_one(self, *args, **kwargs): return self._write_refresh(self._collection.update_one(*args, **kwargs))
    def update_many(self, *args, **kwargs): return self._write_refresh(self._collection.update_many(*args, **kwargs))
    def replace_one(self, *args, **kwargs): return self._write_refresh(self._collection.replace_one(*args, **kwargs))
    def delete_one(self, *args, **kwargs): return self._write_refresh(self._collection.delete_one(*args, **kwargs))
    def delete_many(self, *args, **kwargs): return self._write_refresh(self._collection.delete_many(*args, **kwargs))
    def bulk_write(self, *args, **kwargs): return self._write_refresh(self._collection.bulk_write(*args, **kwargs))


def cache_status() -> dict[str, Any]:
    with _lock:
        return {"enabled": CACHE_ENABLED, "warming": _warming, "ready": len(_ready), "collections": sorted(_ready), "last_error": _last_error}


def preload_cache(collection_names: Iterable[str]) -> None:
    if not CACHE_ENABLED:
        return
    loaded: dict[str, list[dict[str, Any]]] = {}
    ready: set[str] = set()
    for name in collection_names:
        try:
            rows = _load_file(name)
        except Exception:
            continue
        if rows or _path(name).exists():
            loaded[name] = rows
            ready.add(name)
    with _lock:
        _cache.update(loaded)
        _ready.update(ready)


def refresh_collection(name: str, collection) -> None:
    if not CACHE_ENABLED:
        return
    global _last_error
    rows = list(collection.find({}))
    with _lock:
        _cache[name] = rows
        _ready.add(name)
        _save_file(name, rows)
        _last_error = None


def refresh_collection_async(name: str, collection) -> None:
    if not CACHE_ENABLED:
        return
    threading.Thread(target=refresh_collection, args=(name, collection), daemon=True).start()


def warm_cache(collections: Iterable[tuple[str, Any]]) -> None:
    global _warming, _last_error
    if not CACHE_ENABLED:
        return
    with _lock:
        _warming = True
    try:
        for name, collection in collections:
            try:
                refresh_collection(name, collection)
            except Exception as exc:
                with _lock:
                    _last_error = f"{name}: {exc}"
    finally:
        with _lock:
            _warming = False


def warm_cache_async(collections: Iterable[tuple[str, Any]]) -> None:
    threading.Thread(target=warm_cache, args=(list(collections),), daemon=True).start()
