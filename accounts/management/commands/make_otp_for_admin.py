from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

from _base import settings
from accounts.models import User


class Command(BaseCommand):
    help = 'Creates a TOTP device for admin user'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='Username to create OTP for',
            nargs='?'
        )

    def handle(self, *args, **kwargs):
        username = kwargs.get('username')
        if not username:
            raise CommandError('Username is required. Usage: python manage.py make_otp_for_admin <username>')

        try:
            user = User.objects.get(username=username)
            user.is_staff = user.is_superuser = True
            user.save()

            device = TOTPDevice.objects.filter(user=user).first()
            if not device:
                device = TOTPDevice.objects.create(user=user, name='main')
            device.confirmed = True
            print(f'{device.config_url}')
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('Admin user not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
