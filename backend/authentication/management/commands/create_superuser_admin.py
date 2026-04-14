"""
Management command: create_superuser_admin

Creates the initial TenderShield Administrator user.

Usage:
    python manage.py create_superuser_admin \
        --username admin \
        --email admin@example.com \
        --password <secure-password>

Environment variable alternative (non-interactive):
    DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the initial TenderShield Administrator user."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("DJANGO_SUPERUSER_USERNAME"))
        parser.add_argument("--email", default=os.environ.get("DJANGO_SUPERUSER_EMAIL"))
        parser.add_argument("--password", default=os.environ.get("DJANGO_SUPERUSER_PASSWORD"))
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Read credentials from environment variables without prompting.",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        username = options["username"]
        email = options["email"]
        password = options["password"]

        if not options["no_input"]:
            if not username:
                username = input("Username: ").strip()
            if not email:
                email = input("Email: ").strip()
            if not password:
                import getpass
                password = getpass.getpass("Password: ")
                confirm = getpass.getpass("Confirm password: ")
                if password != confirm:
                    raise CommandError("Passwords do not match.")

        if not username:
            raise CommandError("Username is required. Use --username or DJANGO_SUPERUSER_USERNAME.")
        if not email:
            raise CommandError("Email is required. Use --email or DJANGO_SUPERUSER_EMAIL.")
        if not password:
            raise CommandError("Password is required. Use --password or DJANGO_SUPERUSER_PASSWORD.")

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f"User '{username}' already exists. Skipping creation.")
            )
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(
            self.style.SUCCESS(f"Administrator user '{username}' created successfully.")
        )
