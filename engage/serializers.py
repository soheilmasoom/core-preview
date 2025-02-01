from rest_framework import serializers
from .models import Highlight, Story, StoryView

class StorySerializer(serializers.ModelSerializer):
    seen = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = ['id', 'media', 'text', 'seen']

    def get_seen(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.views.filter(user=request.user).exists()
        return False

class HighlightSerializer(serializers.ModelSerializer):
    seen = serializers.BooleanField(read_only=True)
    stories = StorySerializer(many=True, read_only=True)

    class Meta:
        model = Highlight
        fields = ['id', 'title', 'image', 'seen', 'stories']
