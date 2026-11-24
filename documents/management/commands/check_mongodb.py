from django.core.management.base import BaseCommand, CommandError

from smart_document_system.mongodb import MongoConfigurationError, ensure_indexes, ping


class Command(BaseCommand):
    help = 'Verify MongoDB Atlas connectivity and create required indexes.'

    def handle(self, *args, **options):
        try:
            ping()
            ensure_indexes()
        except MongoConfigurationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS('MongoDB Atlas connection and indexes are ready.'))
