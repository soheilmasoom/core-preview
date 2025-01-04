from rest_framework.viewsets import ReadOnlyModelViewSet
from .models import Treasury, PhysicalWithdraw
from .serializers import TreasurySerializer, PhysicalWithdrawSerializer

from rest_framework.permissions import IsAuthenticated


class TreasuryViewSet(ReadOnlyModelViewSet):
    queryset = Treasury.objects.all()
    serializer_class = TreasurySerializer
    permission_classes = [IsAuthenticated]


from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ledger.exceptions import InsufficientBalance


class PhysicalWithdrawViewSet(viewsets.ModelViewSet):
    queryset = PhysicalWithdraw.objects.all()
    serializer_class = PhysicalWithdrawSerializer

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = PhysicalWithdraw.objects.filter(account=self.request.user.account)
        return queryset.order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            withdraw = serializer.save()
            return Response(
                self.get_serializer(withdraw).data,
                status=status.HTTP_201_CREATED
            )
        except InsufficientBalance:
            return Response(
                {'error': 'موجودی کافی نیست'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'error': 'حذف درخواست‌های برداشت مجاز نیست'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def update(self, request, *args, **kwargs):
        return Response(
            {'error': 'به‌روزرسانی مستقیم درخواست‌های برداشت مجاز نیست'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def partial_update(self, request, *args, **kwargs):
        return Response(
            {'error': 'به‌روزرسانی جزئی درخواست‌های برداشت مجاز نیست'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
