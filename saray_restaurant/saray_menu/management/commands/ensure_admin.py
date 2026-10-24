"""``python manage.py ensure_admin`` — create a superuser from environment variables.

Reads ``DJANGO_ADMIN_USER`` and ``DJANGO_ADMIN_PASSWORD`` (and optionally
``DJANGO_ADMIN_EMAIL``). There are deliberately no default credentials: if the
variables are missing the command does nothing. An existing user is left
untouched unless ``--reset-password`` is given.
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create the admin superuser from DJANGO_ADMIN_USER / DJANGO_ADMIN_PASSWORD env vars.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-password', action='store_true',
            help='If the user already exists, set its password from DJANGO_ADMIN_PASSWORD.',
        )

    def handle(self, *args, reset_password=False, **options):
        username = os.environ.get('DJANGO_ADMIN_USER', '').strip()
        password = os.environ.get('DJANGO_ADMIN_PASSWORD', '')
        email = os.environ.get('DJANGO_ADMIN_EMAIL', '').strip()
        if not username or not password:
            self.stdout.write(self.style.WARNING(
                'DJANGO_ADMIN_USER and DJANGO_ADMIN_PASSWORD are not both set; nothing to do.'
            ))
            return

        User = get_user_model()
        user = User.objects.filter(**{User.USERNAME_FIELD: username}).first()
        if user and not reset_password:
            self.stdout.write(f'User "{username}" already exists; left unchanged.')
            return

        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError('Password rejected: ' + ' '.join(exc.messages)) from exc

        if user:
            user.set_password(password)
            user.is_staff = user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Password reset for "{username}".'))
        else:
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" created.'))
