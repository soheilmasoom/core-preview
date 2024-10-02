import uuid
from datetime import datetime, timedelta
from typing import Tuple

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, BadRequest
from django.db.models import Q, Count, F, Value, CharField, Sum
from django.db.models.functions import Cast, TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from openpyxl import Workbook

from accounting.models import TradeRevenue
from accounts.models import TrafficSource, User
from analytics.models import ReportPermission
from analytics.utils.list import join_lists_with_first_element


def _get_report_permission(user: User, group_id: str):
    try:
        group_id = uuid.UUID(group_id)
    except ValueError:
        raise PermissionDenied

    permission = ReportPermission.objects.filter(group_id=group_id, enable=True).first()

    if not permission:
        raise PermissionDenied

    if not user.is_superuser and permission.user != user:
        raise PermissionDenied

    return permission


def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str or '', '%Y-%m-%d').astimezone()
    except ValueError:
        raise BadRequest('Invalid Data')


@login_required
def request_source_analytics(request, group_id: str):
    _get_report_permission(request.user, group_id)

    context = {
        'redirect_url': settings.HOST_URL + f'/analytics/marketing/reports/{group_id}/download/'
    }
    return render(request, 'datetime_form.html', context)


@login_required
def get_source_analytics(request, group_id: str):
    permission = _get_report_permission(request.user, group_id)

    start = parse_date(request.GET.get('start'))
    end = parse_date(request.GET.get('end'))

    if end - start > timedelta(days=30):
        raise BadRequest('Report can export at most 30 days')

    headers, data = get_data(permission, start, end)

    workbook = queryset_to_workbook(headers, data)

    # create a response object
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=reports.xlsx'

    # write workbook to response
    workbook.save(response)

    return response


def get_data(permission: ReportPermission, start: datetime, end: datetime) -> Tuple[list, list]:
    headers = ['date', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'users', 'verified',
               'depositors']

    queryset = TrafficSource.objects.filter(
        utm_source=permission.utm_source,
        utm_medium=permission.utm_medium,
        created__range=[start, end],
        user__account__referral__isnull=True,
    ).annotate(
        date_str=Cast(TruncDate('created'), output_field=CharField())
    ).values(
        'date_str', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'
    ).annotate(
        user_count=Count('user_id', distinct=True),
        verified_count=Count(
            'user_id',
            distinct=True,
            filter=Q(user__level_2_verify_datetime__lte=F('user__date_joined') + Value(timedelta(days=1)))
        ),
        depositor_count=Count(
            'user_id', distinct=True,
            filter=Q(user__first_fiat_deposit_date__lte=F('user__date_joined') + Value(timedelta(days=1))) |
                   Q(user__first_crypto_deposit_date__lte=F('user__date_joined') + Value(timedelta(days=1)))
        )
    ).values_list(
        'date_str', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
        'user_count', 'verified_count', 'depositor_count',
    )

    data = list(queryset)

    if permission.referral_percent_revenue:
        group_by = (
            'date_str', 'account__user__traffic_source__utm_source', 'account__user__traffic_source__utm_medium',
            'account__user__traffic_source__utm_campaign', 'account__user__traffic_source__utm_content',
            'account__user__traffic_source__utm_term'
        )

        revenues = TradeRevenue.objects.filter(
            created__range=[start, end],
            account__user__traffic_source__utm_source=permission.utm_source,
            account__user__traffic_source__utm_medium=permission.utm_medium,
            account__user__account__referral__isnull=True
        ).annotate(
            date_str=Cast(TruncDate('created'), output_field=CharField())
        ).values(*group_by).annotate(
            revenue=Sum((F('fee_revenue') + F('gap_revenue')) * F('value_irt') / F('value')) * permission.referral_percent_revenue / 100
        ).values_list(*group_by, 'revenue')

        data = join_lists_with_first_element(data, list(revenues), n1=len(headers), n2=len(group_by) + 1,
                                             group_len=len(group_by))
        headers.append('revenue')

    return headers, sorted(list(data))


def queryset_to_workbook(headers: list, data: list):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Sheet1'

    # write headers
    for col_num, header in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=col_num)
        cell.value = header

    # write data
    for row_num, row in enumerate(data, 1):
        for col_num, field_name in enumerate(headers, 1):
            cell = sheet.cell(row=row_num+1, column=col_num)
            cell.value = row[col_num-1]

    return workbook
