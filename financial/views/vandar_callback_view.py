from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from financial.direct_debit.getter import get_direct_debit_client
from financial.direct_debit.vandar_client import ExternalAPIError
from financial.models.direct_debit_connection import DirectDebitConnection
from financial.models.direct_debit_gateway import DirectDebitGateway


class VandarCallbackView(APIView):
    authentication_classes = permission_classes = ()

    def get(self, request, *args, **kwargs):
        token = request.GET.get('token')
        authorization_id = request.GET.get('authorization_id')
        status = request.GET.get('status')
        error_code = request.GET.get('error_code')

        if status == "SUCCEED" and token and authorization_id:
            connection = DirectDebitConnection.objects.filter(token=token, deleted=False).first()
            if not connection:
                raise ValidationError(f'شناسه مجوز یافت نشد.')

            if connection.verified:
                return Response({'مجوز برای این شناسه قبلا تایید شده است.'})

            gateway = DirectDebitGateway.live_objects.first()

            if not gateway:
                raise ValidationError('امکان تایید مجوز وجود ندارد.')

            connection.set_auth_id(authorization_id)
            client = get_direct_debit_client(gateway)

            try:
                client.accept_authorization_id(connection)
                return Response({'مجوز با موفقیت تایید شد.'})
            except ExternalAPIError as e:
                raise ValidationError({e})

        elif status == "FAILED":
            raise ValidationError(f' تایید مجوز ناموفق: {error_code}')

        elif status == "FAILED_TO_ACCESS_BANK":
            raise ValidationError('امکان تایید مجوز وجود ندارد.')

        raise ValidationError('مشکلی در تایید مجوز پیش آمده است.')
