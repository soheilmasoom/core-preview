# views.py
from django.db.models import Prefetch
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from .models import Highlight
from .serializers import HighlightSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Story, StoryView


class HighlightListView(ListAPIView):
    serializer_class = HighlightSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return (
            Highlight.objects.get_user_highlights(user)
            .prefetch_related(Prefetch('stories', queryset=Story.objects.all().order_by('order')))
        )


class StorySeenAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        story = get_object_or_404(Story, pk=pk)
        story_view, created = StoryView.objects.get_or_create(user=request.user, story=story)
        if created:
            return Response({'detail': 'Story marked as seen.'}, status=status.HTTP_201_CREATED)
        return Response({'detail': 'Story was already marked as seen.'}, status=status.HTTP_200_OK)
