from rest_framework import serializers
from rest_framework.generics import RetrieveUpdateAPIView

from accounts.models import Company
from ledger.utils.fields import PENDING
from multimedia.fields import FileField


class DocumentsSerializer(serializers.ModelSerializer):
    company_documents = FileField()

    class Meta:
        model = Company
        fields = ('company_documents', 'status',)
        extra_kwargs = {
            'status': {'read_only': True}
        }


class RegisterDocuments(RetrieveUpdateAPIView):
    queryset = Company.objects.all()
    serializer_class = DocumentsSerializer

    def perform_update(self, serializer):
        serializer.save(status=PENDING)

    def get_object(self):
        user = self.request.user
        return self.queryset.get(user=user)
