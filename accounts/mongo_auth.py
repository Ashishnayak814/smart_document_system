"""Django authentication backend backed by the MongoDB users collection."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.hashers import check_password, make_password
from django.utils.crypto import salted_hmac

from smart_document_system.repositories import as_object_id, utcnow
from smart_document_system.mongodb import get_collection


class MongoUser:
    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_staff = False
    is_superuser = False

    def __init__(self, data: dict[str, Any]):
        self._data = data
        self.pk = str(data["_id"])
        self.id = self.pk
        self.username = data["email"]
        self.email = data["email"]
        self.first_name = data.get("first_name", "")
        self.last_name = data.get("last_name", "")
        self.password = data["password"]
        self._meta = _MongoMeta()

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()

    def get_username(self) -> str:
        return self.email

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def get_session_auth_hash(self) -> str:
        return salted_hmac("django.contrib.auth.models.AbstractBaseUser.get_session_auth_hash", self.password).hexdigest()

    def save(self, **changes: Any) -> None:
        changes.pop("update_fields", None)
        changes.setdefault("password", self.password)
        changes.setdefault("email", self.email)
        changes.setdefault("first_name", self.first_name)
        changes.setdefault("last_name", self.last_name)
        get_collection("users").update_one({"_id": as_object_id(self.pk)}, {"$set": {**changes, "updated_at": utcnow()}})
        self._data.update(changes)


class MongoAuthenticationBackend:
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (kwargs.get("email") or username or "").strip().lower()
        if not email or password is None:
            return None
        data = get_collection("users").find_one({"email": email})
        if data and check_password(password, data.get("password", "")):
            return MongoUser(data)
        return None

    def get_user(self, user_id):
        try:
            data = get_collection("users").find_one({"_id": as_object_id(user_id), "is_active": True})
        except ValueError:
            return None
        return MongoUser(data) if data else None


class _MongoPk:
    @staticmethod
    def value_to_string(user: MongoUser) -> str:
        return user.pk


class _MongoMeta:
    pk = _MongoPk()
