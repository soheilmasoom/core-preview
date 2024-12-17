from django.conf import settings
from django_minio_backend import MinioBackend


class PublicMediaStorage(MinioBackend):
    def __init__(self):
        self.bucket_name = settings.MINIO_PUBLIC_MEDIA_FILES_BUCKET
        self.public = True
        super().__init__(bucket_name=self.bucket_name)
