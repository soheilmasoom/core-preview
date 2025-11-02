from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class SkipSignupView(APIView):
    permission_classes = []
    throttle_classes = []

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({
                'msg': 'احراز هویت الزامی است.',
                'code': -1
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        return Response({
            'user': {'id': user.id}
        }, status=status.HTTP_200_OK)
