import copy

from django.contrib.admin import ModelAdmin
from django.contrib.auth import get_permission_codename
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect

from . import M
from .urls import AdminUrl
from .utils import BoolNode
from .utils.array_utils import append, append_list


def evaluate_admin_condition(request, admin, model, condition):

    if not isinstance(condition, BoolNode):
        condition = M(condition)

    return condition.evaluate(request, admin, model)


class AdvancedAdmin(ModelAdmin):
    default_view_condition = None
    default_edit_condition = None
    fields_view_conditions = {}
    fields_edit_conditions = {}

    __fieldsets__ = None

    __readonly_fields__ = [
        # 'get_list_item_initializer',
    ]

    list_permission_exclude_filters = ['id']

    def __init__(self, model, admin_site):
        self.model = model
        self.request = None
        super(AdvancedAdmin, self).__init__(model, admin_site)

    @property
    def current_list_page_full_path(self):
        if not self.request:
            return AdminUrl(model_class=self.model).get_list_url()

        else:
            return self.request.get_full_path()

    def has_list_permission(self, request):
        opts = self.opts
        codename = get_permission_codename("list", opts)
        return request.user.has_perm("%s.%s" % (opts.app_label, codename))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        self.request = request
        return super(AdvancedAdmin, self).change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        self.request = request
        return super(AdvancedAdmin, self).changelist_view(request, extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        self.request = request
        return super(AdvancedAdmin, self).add_view(request, form_url, extra_context)

    def get_add_mode(self, request):
        return request.path.endswith('/add/')

    def get_changelist(self, request, **kwargs):
        if self.has_list_permission(request) or \
                any(map(lambda f: request.GET.get(f), self.list_permission_exclude_filters)):

            return super(AdvancedAdmin, self).get_changelist(request, **kwargs)

        raise PermissionDenied

    def get_fieldsets(self, request, obj=None):
        add_mode = self.get_add_mode(request)

        if self.__fieldsets__ is None:
            self.__fieldsets__ = {}

        if self.__fieldsets__.get(add_mode) is None:
            self.__fieldsets__[add_mode] = super(AdvancedAdmin, self).get_fieldsets(request, obj)

        fieldset = copy.deepcopy(self.__fieldsets__[add_mode])

        # removing fields with conditions
        to_remove_fields = self.get_to_remove_fields(request, obj)

        for fields_data in fieldset:
            fields = fields_data[1]['fields']
            fields_data[1]['fields'] = [f for f in fields if f not in to_remove_fields]

        return fieldset

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = self.__readonly_fields__ + self.get_should_be_readonly_fields(request, obj)

        readonly = super(AdvancedAdmin, self).get_readonly_fields(request, obj)

        return append_list(readonly, readonly_fields, unique=True)

    # def get_list_display(self, request):
    #     list_display = super(AdvancedAdmin, self).get_list_display(request)
    #
    #     return append(list_display, 'get_list_item_initializer')

    def get_to_remove_fields(self, request, obj):
        to_remove_fields = []

        for (field, view_condition) in self.fields_view_conditions.items():
            if view_condition is None:
                continue

            if not evaluate_admin_condition(request, self, obj, view_condition):
                to_remove_fields.append(field)

        if self.default_view_condition is not None:
            remaining_fields = set(self._get_fields(request, obj)) - set(self.fields_view_conditions)

            for field in remaining_fields:
                if not evaluate_admin_condition(request, self, obj, self.default_view_condition):
                    to_remove_fields.append(field)

        return to_remove_fields

    def _get_fields(self, request, obj) -> set:
        fields = []
        fieldsets = self.get_fieldsets(request, obj)

        for fs in fieldsets:
            fields += fs[1]['fields']

        return set(fields)

    def get_should_be_readonly_fields(self, request, obj):
        should_be_readonly_fields = []

        for (field, edit_condition) in self.fields_edit_conditions.items():
            if edit_condition is None:
                continue

            if not evaluate_admin_condition(request, self, obj, edit_condition):
                should_be_readonly_fields.append(field)

        if self.default_edit_condition is not None:
            default_condition = self.default_edit_condition
            self.default_edit_condition = None
            remaining_fields = set(self._get_fields(request, obj)) - set(self.fields_edit_conditions)
            self.default_edit_condition = default_condition

            for field in remaining_fields:
                if not evaluate_admin_condition(request, self, obj, self.default_edit_condition):
                    should_be_readonly_fields.append(field)

        return should_be_readonly_fields

    def response_change(self, request, obj):
        _next = request.GET.get('next', None)

        if '_continue' in request.POST or not _next:
            return super(AdvancedAdmin, self).response_change(request, obj)

        return HttpResponseRedirect(_next)

    def response_add(self, request, obj, post_url_continue=None):
        _next = request.GET.get('next', None)

        if '_continue' in request.POST or not _next:
            return super(AdvancedAdmin, self).response_add(request, obj, post_url_continue)

        return HttpResponseRedirect(_next)

    def list_item_init(self, obj):
        pass

    def get_list_item_initializer(self, obj):
        self.list_item_init(obj)
        return ""
    get_list_item_initializer.short_description = ""
