from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from accounts.models import SystemConfig
from .models import Treasury, PhysicalWithdraw
from ledger.exceptions import InsufficientBalance
from .serializers import PhysicalWithdrawSerializer, TreasurySerializer


class TreasuryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        treasuries = Treasury.objects.all()
        serializer = TreasurySerializer(treasuries, many=True)
        return Response(serializer.data)


class PhysicalWithdrawListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        withdraws = PhysicalWithdraw.objects.filter(
            account=request.user.account
        ).order_by('-created_at')
        serializer = PhysicalWithdrawSerializer(withdraws, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PhysicalWithdrawSerializer(
            data=request.data,
            context={'request': request}
        )
        try:
            serializer.is_valid(raise_exception=True)
            withdraw = serializer.save()
            return Response(
                PhysicalWithdrawSerializer(withdraw).data,
                status=status.HTTP_201_CREATED
            )
        except ValidationError as e:
            error_msg = str(e.detail['amount'][0]) if 'amount' in e.detail else str(e)
            return Response(
                {'error': error_msg},
                status=status.HTTP_400_BAD_REQUEST
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


class PhysicalWithdrawDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return PhysicalWithdraw.objects.get(
                pk=pk,
                account=self.request.user.account
            )
        except PhysicalWithdraw.DoesNotExist:
            raise ValidationError("Withdraw request not found")

    def get(self, request, pk):
        withdraw = self.get_object(pk)
        serializer = PhysicalWithdrawSerializer(withdraw)
        return Response(serializer.data)


class PhysicalWithdrawInitView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        config = SystemConfig.get_system_config()
        return Response({
            'min_physical_gold_withdraw': config.min_physical_gold_withdraw,
            'min_physical_silver_withdraw': config.min_physical_silver_withdraw
        })
