from django_minio_backend import MinioBackend


class PublicMediaStorage(MinioBackend):
    bucket_name = 'core-media-public'
    public = True

    def __init__(self):
        super(PublicMediaStorage, self).__init__(bucket_name=self.bucket_name)
