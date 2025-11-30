import urllib

import django
import django.db.models as models
from django.contrib.contenttypes.models import ContentType

if django.VERSION[0] == 1:
    from django.core import urlresolvers
else:
    from django.urls import reverse as urlresolvers


class AdminUrl:

    def __init__(self, model_class=None, pk=None, model: models.Model = None):

        if model and model_class:
            raise ValueError("only one of model and model_class should be passed to constructor")

        self.pk = None

        if model:
            self.content_type = ContentType.objects.get_for_model(model.__class__)
            self.pk = model.pk

        if model_class:
            self.content_type = ContentType.objects.get_for_model(model_class)

        if pk:
            self.pk = pk

    @staticmethod
    def _append_to_url(url, get_params: dict=None, _next: str=None) -> str:

        if not get_params:
            get_params = {}

        if _next:
            get_params['next'] = _next

        params = urllib.parse.urlencode(get_params)

        if len(params) > 0:
            url += '?' + params

        return url

    def get_change_url(self, get_params: dict=None, _next: str=None) -> str:

        if not self.pk:
            raise ValueError("pk not set")

        url_name = "admin:%s_%s_change" % (self.content_type.app_label, self.content_type.model)
        url = urlresolvers.reverse(url_name, args=(self.pk,))

        return AdminUrl._append_to_url(url, get_params, _next)

    def get_list_url(self, get_params: dict=None, _next: str=None) -> str:
        url_name = "admin:%s_%s_changelist" % (self.content_type.app_label, self.content_type.model)
        url = urlresolvers.reverse(url_name)

        return AdminUrl._append_to_url(url, get_params, _next)

    def get_add_url(self, get_params: dict=None, _next: str=None) -> str:
        url_name = "admin:%s_%s_add" % (self.content_type.app_label, self.content_type.model)
        url = urlresolvers.reverse(url_name)

        return AdminUrl._append_to_url(url, get_params, _next)
