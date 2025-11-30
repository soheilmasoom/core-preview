from rest_framework.exceptions import ValidationError
from rest_framework.generics import CreateAPIView
from rest_framework.serializers import ModelSerializer

from accounts.models import Consultation
from ledger.utils.fields import PENDING


class ConsultationSerializer(ModelSerializer):

    class Meta:
        model = Consultation
        fields = ('description',)
        extra_kwargs = {
            'description': {'write_only': True}
        }


class ConsultationView(CreateAPIView):
    serializer_class = ConsultationSerializer

    def perform_create(self, serializer):
        user = self.request.user

        if Consultation.objects.filter(
            user=user,
            status=PENDING
        ).exists():
            raise ValidationError('شما در حال حاضر درخواست مشاوره‌ی پردازش نشده‌ای دارید.')

        serializer.save(user=user)
