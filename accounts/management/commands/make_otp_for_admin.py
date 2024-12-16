from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice
from accounts.models import User

class Command(BaseCommand):
    help = 'Creates a TOTP device for admin user'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='Username to create OTP for',
            nargs='?'  # Makes the argument optional
        )

    def handle(self, *args, **kwargs):
        username = kwargs.get('username')
        if not username:
            raise CommandError('Username is required. Usage: python manage.py make_otp_for_admin <username>')

        try:
            user = User.objects.get(username=username)
            device = TOTPDevice.objects.create(user=user, name='main')
            config_url = device.config_url
            self.stdout.write(self.style.SUCCESS(f'OTP Config URL: {config_url}'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('Admin user not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))