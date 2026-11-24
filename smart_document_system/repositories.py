"""Small, reusable PyMongo CRUD primitives used by the application."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from bson import ObjectId
from pymongo.collection import Collection

from .mongodb import get_collection


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_object_id(value: str | ObjectId) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if not isinstance(value, str) or not ObjectId.is_valid(value):
        raise ValueError("Invalid MongoDB ObjectId")
    return ObjectId(value)


class MongoRepository:
    def __init__(self, collection: str | Collection):
        self._collection_name = collection if isinstance(collection, str) else None
        self._collection = None if isinstance(collection, str) else collection

    @property
    def collection(self) -> Collection:
        if self._collection is None:
            self._collection = get_collection(self._collection_name)
        return self._collection

    def insert(self, record: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        record = {**record, "created_at": record.get("created_at", now), "updated_at": now}
        result = self.collection.insert_one(record)
        return self.get(result.inserted_id) or record | {"_id": result.inserted_id}

    def get(self, record_id: str | ObjectId, *, extra_filter: dict[str, Any] | None = None) -> dict[str, Any] | None:
        query = {"_id": as_object_id(record_id), **(extra_filter or {})}
        return self.collection.find_one(query)

    def many(self, filters: dict[str, Any] | None = None, *, sort: Iterable[tuple[str, int]] = ()) -> list[dict[str, Any]]:
        cursor = self.collection.find(filters or {})
        sort = list(sort)
        if sort:
            cursor = cursor.sort(sort)
        return list(cursor)

    def update(self, record_id: str | ObjectId, changes: dict[str, Any], *, extra_filter: dict[str, Any] | None = None) -> dict[str, Any] | None:
        changes = {**changes, "updated_at": utcnow()}
        self.collection.update_one({"_id": as_object_id(record_id), **(extra_filter or {})}, {"$set": changes})
        return self.get(record_id, extra_filter=extra_filter)

    def delete(self, record_id: str | ObjectId, *, extra_filter: dict[str, Any] | None = None) -> bool:
        result = self.collection.delete_one({"_id": as_object_id(record_id), **(extra_filter or {})})
        return result.deleted_count == 1

    def search(self, filters: dict[str, Any], *, sort: Iterable[tuple[str, int]] = ()) -> list[dict[str, Any]]:
        return self.many(filters, sort=sort)

    def count(self, filters: dict[str, Any] | None = None) -> int:
        return self.collection.count_documents(filters or {})
