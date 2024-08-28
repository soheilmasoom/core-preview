from financial.models import PaymentRequest, Payment as PaymentModel

def add_user_to_payment_request():
    batch_size = 1000
    offset = 0

    while True:
        payments = list(
            PaymentModel.objects.select_related('paymentrequest')
            .filter()
            .order_by('id')[offset:offset + batch_size]
        )

        if not payments:
            break

        payment_requests_to_update = []

        for payment in payments:
            payment.paymentrequest.user = payment.user
            payment_requests_to_update.append(payment.paymentrequest)

        PaymentRequest.objects.bulk_update(payment_requests_to_update, ['user'])

        offset += batch_size
        print(f"Processed {offset} payments")

    print("Migration completed.")
