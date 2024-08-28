from rest_framework.response import Response
from rest_framework.views import APIView

from search.models import SearchHistory
from search.utils import get_search_result


class SearchView(APIView):
    def get(self, request):
        query = request.GET.get('q', '')

        result = get_search_result(query)

        SearchHistory.objects.create(
            account=request.user.get_account(),
            query=query,
            result=result
        )
        return Response(data=result, status=200)
