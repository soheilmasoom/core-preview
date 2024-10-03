from django.utils.safestring import mark_safe
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse


def anchor_tag(title, url, style="", target="", _class=""):
    return mark_safe("<a href='%s' target='%s' style='%s' class='%s'>%s</a>" % (url, target, style, _class, title))


def url_to_edit_object(obj):
    return settings.HOST_URL + reverse('admin:%s_%s_change' % (obj._meta.app_label,  obj._meta.model_name),  args=[obj.id] )


def url_to_admin_list(obj, filters: dict = None):
    url = settings.HOST_URL + reverse('admin:%s_%s_changelist' % (obj._meta.app_label,  obj._meta.model_name))

    if filters:
        url += '?' + urlencode(filters)

    return url


def admin_page_anchor(obj, title: str = '', change: bool = True):
    if change:
        url = url_to_edit_object(obj)
    else:
        url = url_to_admin_list(obj)

    return anchor_tag(title or str(obj), url)
