from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView


class QuizPassedView(APIView):

    def patch(self, request, *args, **kwargs):
        user = request.user
        user.margin_quiz_pass_date = timezone.now()
        user.save(update_fields=['margin_quiz_pass_date'])

        return Response('done!')