import operator

from rest_framework.response import Response
from rest_framework.views import APIView

from financial.models import Payment, FiatWithdrawRequest
from ledger.models import Transfer


class RecentTransactionsView(APIView):

    def get(self, request):
        user = request.user
        print(user.id)
        account = user.get_account()

        transactions = [
            {
                'created': t.created,
                'coin': t.wallet.asset.symbol,
                'amount': t.amount,
                'type': 'deposit' if t.deposit else 'withdraw',
                'status': t.status
            } for t in Transfer.objects.filter(wallet__account=account).order_by('-created')
                                       .select_related('wallet__asset')[:5]
        ]

        transactions.extend([
            {
                'created': p.created,
                'coin': 'IRT',
                'amount': p.amount,
                'type': 'deposit',
                'status': p.status
            } for p in Payment.objects.filter(user=user).order_by('-created')[:5]
        ])

        transactions.extend([
            {
                'created': w.created,
                'coin': 'IRT',
                'amount': w.amount,
                'type': 'withdraw',
                'status': w.status
            } for w in FiatWithdrawRequest.objects.filter(bank_account__user=user).order_by('-created')[:5]
        ])

        transactions.sort(key=operator.itemgetter('created'), reverse=True)

        return Response(transactions[:5])
