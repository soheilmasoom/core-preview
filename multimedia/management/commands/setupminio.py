import json
import os

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import BaseCommand
from minio import Minio
from minio.error import S3Error


class Command(BaseCommand):
    help = "Collect static files and initialize MinIO buckets."

    def handle(self, *args, **options):
        self.init_minio_buckets()
        self.send_coins_logo()

    def init_minio_buckets(self):
        # Create MinIO client
        minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_HTTPS,
        )

        # List of buckets to ensure they exist
        buckets = settings.MINIO_PRIVATE_BUCKETS + settings.MINIO_PUBLIC_BUCKETS

        for bucket_name in buckets:
            try:
                if not minio_client.bucket_exists(bucket_name):
                    minio_client.make_bucket(bucket_name)
                    self.stdout.write(self.style.SUCCESS(f"Bucket '{bucket_name}' created successfully."))

                    # Set bucket policy to public if it is in the public buckets list
                    if bucket_name in settings.MINIO_PUBLIC_BUCKETS:
                        self.set_public_bucket_policy(minio_client, bucket_name)

                else:
                    self.stdout.write(self.style.WARNING(f"Bucket '{bucket_name}' already exists."))
            except S3Error as e:
                self.stdout.write(self.style.ERROR(f"Error occurred while creating bucket '{bucket_name}': {e}"))

    def set_public_bucket_policy(self, minio_client, bucket_name):
        # Public policy configuration
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                }
            ]
        }

        # Set the public policy on the bucket
        try:
            minio_client.set_bucket_policy(bucket_name, json.dumps(policy))
            self.stdout.write(self.style.SUCCESS(f"Bucket '{bucket_name}' policy set to public."))
        except S3Error as e:
            self.stdout.write(self.style.ERROR(f"Error occurred while setting bucket policy for '{bucket_name}': {e}"))

    def send_coins_logo(self):
        minio_client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_HTTPS,
        )

        for coin_name in os.listdir('static/coins'):
            static_file_path = finders.find(f'coins/{coin_name}')
            if static_file_path:
                with open(static_file_path, 'rb') as file_data:
                    file_name = f"coins/logo/{coin_name}"  # Define the destination path in the bucket
                    minio_client.put_object(
                        settings.MINIO_PUBLIC_MEDIA_FILES_BUCKET,
                        file_name,
                        file_data,
                        length=-1,
                        part_size=10 * 1024 * 1024
                    )
                    print(f"Successfully uploaded {coin_name}")
            else:
                print(f"File not found in static files: {coin_name}")
