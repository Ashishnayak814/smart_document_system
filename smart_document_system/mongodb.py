"""Reusable MongoDB Atlas connection and collection/index setup."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

load_dotenv()


class MongoConfigurationError(RuntimeError):
    """Raised when MongoDB is not configured or cannot be reached."""


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        raise MongoConfigurationError("MONGODB_URI is not configured.")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as exc:
        client.close()
        raise MongoConfigurationError("MongoDB Atlas is unavailable.") from exc
    return client


def get_database() -> Database:
    database_name = os.getenv("MONGODB_DATABASE", "smart_document_db").strip()
    if not database_name:
        raise MongoConfigurationError("MONGODB_DATABASE is not configured.")
    return get_client()[database_name]


def get_collection(name: str) -> Collection:
    if name not in {"users", "documents", "classification_results", "activity_logs", "password_reset_tokens"}:
        raise ValueError(f"Unsupported MongoDB collection: {name}")
    return get_database()[name]


def ensure_indexes() -> None:
    """Create safe, repeatable indexes; this never drops data or indexes."""
    get_collection("users").create_index([("email", ASCENDING)], unique=True, name="email_unique")
    documents = get_collection("documents")
    documents.create_index([("owner_id", ASCENDING), ("uploaded_at", DESCENDING)], name="owner_recent")
    documents.create_index([("owner_id", ASCENDING), ("category", ASCENDING)], name="owner_category")
    documents.create_index([("original_filename", ASCENDING)], name="original_filename")
    results = get_collection("classification_results")
    results.create_index([("document_id", ASCENDING)], unique=True, name="document_unique")
    results.create_index([("user_id", ASCENDING), ("processed_at", DESCENDING)], name="user_recent")
    get_collection("activity_logs").create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_activity")
    get_collection("password_reset_tokens").create_index([("token_hash", ASCENDING)], unique=True, name="token_unique")
    get_collection("password_reset_tokens").create_index([("expires_at", ASCENDING)], expireAfterSeconds=0, name="token_expiry")


def ping() -> bool:
    get_database().command("ping")
    return True
