from django.db import models
from django.contrib import admin
from accounts.admin_guard.html_tags import anchor_tag, admin_page_anchor
from accounts.admin_guard.html_tags import url_to_edit_object
from accounts.models import User


class AdminTracker(models.Model):
    created = models.DateTimeField(auto_now_add=True, verbose_name="Created")
    admin = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Admin User", related_name='admin_actions')
    model_name = models.CharField(max_length=255, verbose_name="Model")
    object_id = models.CharField(max_length=255, null=True, blank=True, verbose_name="Object ID")
    url = models.CharField(max_length=1024, verbose_name="URL")
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name="User", related_name='tracked_by_admin')

    def __str__(self):
        return f"{self.admin} {self.model_name} at {self.created}"

    def admin_link(self, obj):
        return admin_page_anchor(obj.admin, change=True) if obj.admin else "N/A"
    admin_link.short_description = "Admin"

    def user_link(self, obj):
        return admin_page_anchor(obj.user, change=True) if obj.user else "N/A"
    user_link.short_description = "User"

    def object_link(self, obj):
        if obj.object_id and obj.model_name:
            dummy_object = type('DummyObject', (), {'_meta': type('Meta', (), {'app_label': 'app_name', 'model_name': obj.model_name.lower()}), 'id': obj.object_id})
            return anchor_tag(obj.object_id, url_to_edit_object(dummy_object), target='_blank')
        return "N/A"
    object_link.short_description = "Object"
