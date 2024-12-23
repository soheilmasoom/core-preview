from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from .models import Treasury
from .serializers import TreasurySerializer

class TreasuryViewSet(ReadOnlyModelViewSet):
    queryset = Treasury.objects.all()
    serializer_class = TreasurySerializer
    permission_classes = [IsAuthenticated]