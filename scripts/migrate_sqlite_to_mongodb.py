"""Non-destructive SQLite -> MongoDB migration for the existing project.

Dry-run is the default. Use --apply only after reviewing the printed counts.
The old db.sqlite3 and media files are never deleted or modified.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import django
from bson import ObjectId


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Insert records into MongoDB; omit for dry-run')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_document_system.settings')
    django.setup()

    from django.contrib.auth.models import User
    from documents.models import Document as SqliteDocument
    from smart_document_system.mongodb import ensure_indexes, get_collection
    from smart_document_system.repositories import utcnow

    users = list(User.objects.all())
    documents = list(SqliteDocument.objects.select_related('owner').all())
    print(f'Found {len(users)} SQLite users and {len(documents)} SQLite documents.')
    if not args.apply:
        print('Dry-run only. No MongoDB records were changed. Re-run with --apply to migrate.')
        return 0

    ensure_indexes()
    users_collection = get_collection('users')
    docs_collection = get_collection('documents')
    user_ids: dict[int, ObjectId] = {}
    for user in users:
        existing = users_collection.find_one({'email': user.email.lower()})
        if existing:
            user_ids[user.pk] = existing['_id']
            continue
        result = users_collection.insert_one({
            'email': user.email.lower(), 'password': user.password,
            'first_name': user.first_name, 'last_name': user.last_name,
            'is_active': user.is_active, 'legacy_sqlite_id': user.pk,
            'created_at': utcnow(), 'updated_at': utcnow(),
        })
        user_ids[user.pk] = result.inserted_id

    inserted = 0
    for document in documents:
        owner_id = user_ids.get(document.owner_id)
        if owner_id is None:
            continue
        if docs_collection.find_one({'legacy_sqlite_id': document.pk}):
            continue
        file_name = Path(document.file.name).name
        docs_collection.insert_one({
            'owner_id': owner_id, 'name': document.name,
            'original_filename': file_name, 'file_type': Path(file_name).suffix.lstrip('.').upper(),
            'storage_path': document.file.name, 'category': document.category,
            'description': document.description, 'uploaded_at': document.uploaded_at,
            'processing_status': 'migrated', 'legacy_sqlite_id': document.pk,
            'created_at': document.uploaded_at, 'updated_at': document.uploaded_at,
        })
        inserted += 1
    print(f'Migration complete: {len(user_ids)} users available, {inserted} documents inserted.')
    print('SQLite data and local media were preserved.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
