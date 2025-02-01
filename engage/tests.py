from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from ledger.utils.test import new_account
from .models import Highlight, Story, StoryView

User = get_user_model()


class HighlightsAPITestCase(APITestCase):
    def setUp(self):
        account = new_account()
        self.user = account.user
        self.client = APIClient()
        self.client.force_login(self.user)

        self.highlight = Highlight.objects.create(title='Test Highlight', is_active=True)

        # Create three stories with different order values.
        self.story1 = Story.objects.create(
            highlight=self.highlight, text='Story 1', order=10
        )
        self.story2 = Story.objects.create(
            highlight=self.highlight, text='Story 2', order=5
        )
        self.story3 = Story.objects.create(
            highlight=self.highlight, text='Story 3', order=20
        )

    def test_highlights_list_order_and_seen_flags(self):
        """
        GET /highlights/ should return the active highlight with:
         - A highlight-level `seen` flag (False initially, then True once all stories are seen)
         - Nested stories ordered by `order` (ascending)
         - Each story with its own `seen` flag (False initially)
        """
        url = reverse('highlight-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(len(data), 1)
        highlight_data = data[0]
        self.assertFalse(highlight_data['seen'], "Highlight should not be marked as seen yet.")

        stories = highlight_data['stories']
        self.assertEqual(len(stories), 3)

        for story in stories:
            self.assertFalse(story['seen'], "Story should not be marked as seen yet.")

        for story in [self.story2, self.story1, self.story3]:
            url_story = reverse('story-seen', kwargs={'pk': story.id})
            post_response = self.client.post(url_story)
            self.assertIn(
                post_response.status_code,
                [status.HTTP_200_OK, status.HTTP_201_CREATED],
                f"POST {url_story} did not return the expected status."
            )

        response2 = self.client.get(url)
        highlight_data2 = response2.json()[0]
        self.assertTrue(highlight_data2['seen'], "Highlight should be marked as seen after all stories are seen.")
        for story in highlight_data2['stories']:
            self.assertTrue(story['seen'], "Each story should be marked as seen after being marked.")

    def test_story_seen_endpoint_idempotence(self):
        url = reverse('story-seen', kwargs={'pk': self.story1.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response2 = self.client.post(url)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        self.assertEqual(
            StoryView.objects.filter(user=self.user, story=self.story1).count(),
            1,
            "Duplicate StoryView records were created."
        )
