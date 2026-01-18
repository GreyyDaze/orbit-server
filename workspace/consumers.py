
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class BoardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.board_id = self.scope['url_route']['kwargs']['board_id']
        self.room_group_name = f'board_{self.board_id}'
        print(f"WS CONNECT: board_id={self.board_id}")

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        print(f"WS ACCEPTED: board_id={self.board_id}")

    async def disconnect(self, close_code):
        print(f"WS DISCONNECT: board_id={self.board_id}, code={close_code}")
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket (Optional: for cursor tracking or temp moves)
    async def receive(self, text_data):
        pass

    # Receive message from room group (Broadcasts from Signals)
    async def board_update(self, event):
        # Use Django's JSON encoder to handle UUIDs and datetimes
        from django.core.serializers.json import DjangoJSONEncoder
        await self.send(text_data=json.dumps(event['data'], cls=DjangoJSONEncoder))
