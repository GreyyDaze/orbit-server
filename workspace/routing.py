
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/board/(?P<board_id>[0-9a-f-]+)/$', consumers.BoardConsumer.as_asgi()),
]
