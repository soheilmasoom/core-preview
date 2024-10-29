from django.db import models

from uuid import uuid4

from multimedia.storage import PublicMediaStorage


class Image(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(default=uuid4, unique=True)
    image = models.ImageField()

    def get_url(self):
        return self.image.url

    def __str__(self):
        return f'Image {self.id}'


class PublicVideo(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=64)
    video = models.FileField(storage=PublicMediaStorage(), upload_to='videos/')

    def get_url(self):
        return self.video.url

    def __str__(self):
        return f'{self.id}- {self.title}'


class File(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(default=uuid4, unique=True)
    file = models.FileField()
    
    def get_absolute_file_url(self):
        return self.file.url
    
    def __str__(self):
        return f'File {self.id}'
