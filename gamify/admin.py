from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Q
from django.utils import timezone

from gamify import models
from gamify.models import UserMission, Task
from gamify.utils import clone_mission_template, check_prize_achievements


@admin.register(models.MissionJourney)
class MissionJourneyAdmin(admin.ModelAdmin):
    list_display = ('name', 'active', 'default')
    list_editable = ('active', 'default')


@admin.register(models.Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('mission', 'asset', 'amount', 'voucher')


class TaskInline(admin.TabularInline):
    fields = ('scope', 'type', 'max', 'title', 'link', 'app_link', 'description', 'level', 'order')
    model = models.Task
    extra = 0


class AchievementInline(admin.TabularInline):
    fields = ('asset', 'amount', 'voucher')
    model = models.Achievement
    extra = 0


@admin.register(models.MissionTemplate)
class MissionTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'journey', 'active', 'get_tasks', 'achievement', 'order')
    list_editable = ('order', 'active')
    inlines = (TaskInline, AchievementInline)
    actions = ('clone_mission', )
    list_filter = ('journey', 'active')
    ordering = ('journey', 'order', 'id')

    @admin.display(description='tasks')
    def get_tasks(self, mission: models.MissionTemplate):
        return ','.join(mission.task_set.values_list('scope', flat=True))

    @admin.action(description='Clone', permissions=['change'])
    def clone_mission(self, request, queryset):
        for mission in queryset:  # type: models.MissionTemplate
            mission.active = False
            clone_mission_template(mission)


class UserMissionExpiredFilter(SimpleListFilter):
    title = 'منقضی شده'
    parameter_name = 'expired'

    def lookups(self, request, model_admin):
        return [('1', 'بله'), ('0', 'خیر')]

    def queryset(self, request, queryset):
        action = self.value()

        if action is None:
            return queryset

        q = Q(mission__expiration__isnull=False, mission__expiration__lt=timezone.now())

        if action == '0':
            q = ~q

        return queryset.filter(q)


@admin.register(UserMission)
class UserMissionAdmin(admin.ModelAdmin):
    list_display = ('created', 'user', 'mission', 'finished', 'expired', 'get_expiration')
    list_filter = ('mission', 'finished', UserMissionExpiredFilter)
    actions = ('check_achievement', )
    raw_id_fields = ('user', )
    search_fields = ('user__phone', )

    @admin.display(description='expiration', ordering='mission__expiration')
    def get_expiration(self, user_mission: UserMission):
        return user_mission.mission.expiration

    @admin.action(description='بررسی جایزه', permissions=['view'])
    def check_achievement(self, request, queryset):
        for user_mission in queryset:
            user_mission.check_achievements()


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('mission', 'scope', 'title', 'type', 'max')
    list_filter = ('mission', )
