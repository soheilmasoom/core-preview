from financial.models import PaymentRequest

def add_user_to_payment_request():
    payment_requests = PaymentRequest.objects.select_related('bank_card', 'bank_card__user')
    updated_requests = []
    for payment_request in payment_requests:
        if payment_request.bank_card and payment_request.bank_card.user:
            payment_request.user = payment_request.bank_card.user
            updated_requests.append(payment_request)
    PaymentRequest.objects.bulk_update(updated_requests, ['user'])
