from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import User


@receiver(post_save, sender=User)
def user_profile_updated(sender, instance, created, **kwargs):
    """
    When a user updates their profile (username/display name),
    broadcast updates for all notes they've created on any board.
    
    This ensures that name changes appear instantly on all connected clients.
    """
    if created:
        return  # Don't broadcast on user creation
    
    # Get all notes created by this user's ghost profile
    if hasattr(instance, 'ghost_profile') and instance.ghost_profile:
        from workspace.models import Note
        from workspace.serializers import NoteSerializer
        
        notes = Note.objects.filter(creator_ghost=instance.ghost_profile)
        
        # Broadcast updates for each note on its respective board
        for note in notes:
            data = NoteSerializer(note).data
            
            # Import the broadcast utility
            import uuid
            def stringify(obj):
                if isinstance(obj, dict):
                    return {k: stringify(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [stringify(item) for item in obj]
                if isinstance(obj, uuid.UUID):
                    return str(obj)
                return obj
            
            safe_data = stringify(data)
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'board_{note.board.id}',
                {
                    'type': 'board_update',
                    'data': {
                        'type': 'NOTE_UPDATED',
                        'payload': safe_data
                    }
                }
            )
