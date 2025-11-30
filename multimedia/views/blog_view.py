import requests
from rest_framework.response import Response
from rest_framework.views import APIView


def get_blog_summary(limit: int = 3):
    url = f'https://blog.raastin.com/wp-json/wp/v2/posts?page=1&per_page={limit}&_fields=yoast_head_json'
    resp = requests.get(url, timeout=10)
    posts = resp.json()

    return [
        {
            'title': p['yoast_head_json']['og_title'],
            'description': p['yoast_head_json']['og_description'],
            'url': p['yoast_head_json']['og_url'],
            'image': {
                'url': p['yoast_head_json']['og_image'][0]['url']
            },
        } for p in posts
    ]


class LatestBlogPostsView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        limit = min(int(request.query_params.get('limit', 3)), 10)
        return Response(get_blog_summary(limit))
