from django.core.management.base import BaseCommand, CommandError
from subprocess import Popen
from sys import stdout, stdin, stderr
import time
import os
import signal
from market.utils.redis import socket_server_redis


class Command(BaseCommand):
    help = 'Run Update Market Redis'

    def handle(self, *args, **options):
        if not socket_server_redis.get('market_depth_snapshot_liveness'):
            raise CommandError('Liveness failed')
        else:
            self.stdout.write('Liveness Ok!')
