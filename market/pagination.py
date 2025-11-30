from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response


class FastLimitOffsetPagination(LimitOffsetPagination):
    max_limit = 20

    def paginate_queryset(self, queryset, request, view=None):
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None

        self.count = 10 ** 5
        self.offset = self.get_offset(request)
        self.request = request

        return list(queryset[self.offset:self.offset + self.limit])

    def get_paginated_response(self, data):
        return Response({
            'results': data
        })
