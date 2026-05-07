"""
Django command to wait for the configured database connection.
"""

import time

from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, OperationalError, connections


class Command(BaseCommand):
    """Block until the default Django database connection is available."""

    help = "Wait for the configured default database to become available."

    def handle(self, *args, **options):
        self.stdout.write("Waiting for database...")
        connection = connections[DEFAULT_DB_ALIAS]

        while True:
            try:
                connection.ensure_connection()
                break
            except OperationalError:
                self.stdout.write("Database unavailable, waiting 1 second...")
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS("Database available!"))
