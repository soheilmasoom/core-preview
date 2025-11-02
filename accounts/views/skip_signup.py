# This file can be deleted or kept empty
# User creation now happens in verify endpoint
# This endpoint is no longer needed

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status


class SkipSignupView(APIView):
    """
    DEPRECATED: User creation now happens in PhoneLoginVerifyView.
    This endpoint is kept for backwards compatibility but does nothing.
    """
    permission_classes = []

    def post(self, request):
        return Response({
            'msg': 'This endpoint is deprecated. User is created in verify endpoint.',
            'code': -1
        }, status=status.HTTP_410_GONE)