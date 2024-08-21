from financial.models import PaymentRequest, Payment

def add_user_to_payment_request():
    batch_size = 1000
    offset = 0

    while True:
        payments_list = list(
            Payment.objects.select_related('paymentrequest')
            .filter()
            .order_by('id')[offset:offset + batch_size]
        )

        if not payments_list:
            break

        payment_requests_to_update = []

        for payment_obj in payments_list:
            payment_obj.payment_request.user = payment_obj.user
            payment_requests_to_update.append(payment_obj.payment_request)

        PaymentRequest.objects.bulk_update(payment_requests_to_update, ['user'])

        offset += batch_size
