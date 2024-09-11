from django_minio_backend import MinioBackend


class PublicMediaStorage(MinioBackend):
    bucket_name = 'core-media-public'
    public = True
