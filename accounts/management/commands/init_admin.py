from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.management.base import BaseCommand
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class Command(BaseCommand):
    help = 'Create the power-user account (if missing) and print a one-time password-set link.'

    def handle(self, *args, **options):
        email = next(iter(settings.POWER_USER_EMAILS))
        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        if created:
            user.set_unusable_password()
            user.save()
            self.stdout.write(f'Created user: {email}')
        else:
            self.stdout.write(f'User exists: {email}')

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        # Build link — uses ALLOWED_HOSTS[0] as base when outside a request
        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost:8000'
        scheme = 'https' if not settings.DEBUG else 'http'
        link = f'{scheme}://{host}/accounts/password-reset/confirm/{uid}/{token}/'

        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write('  ONE-TIME PASSWORD-SET LINK (valid 3 days)')
        self.stdout.write('=' * 60)
        self.stdout.write(link)
        self.stdout.write('=' * 60)
        self.stdout.write('')
