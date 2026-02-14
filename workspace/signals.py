
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Note, Board, Upvote, BoardInvite, AccessRequest
from .serializers import NoteSerializer

def broadcast_update(board_id, message_type, data):
    # Ensure board_id is string
    b_id = str(board_id)
    
    # Simple recursive stringifier for UUIDs and potentially other types
    def stringify(obj):
        if isinstance(obj, dict):
            return {k: stringify(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [stringify(item) for item in obj]
        import uuid
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return obj

    safe_data = stringify(data)
    
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'board_{b_id}',
        {
            'type': 'board_update',
            'data': {
                'type': message_type,
                'payload': safe_data
            }
        }
    )

@receiver(post_save, sender=Note)
def note_saved(sender, instance, created, **kwargs):
    # If it's a new note or an update
    # We serialize it to send full current state
    # Note: Serializer might need request context, but we use basic here
    data = NoteSerializer(instance).data
    msg_type = 'NOTE_CREATED' if created else 'NOTE_UPDATED'
    broadcast_update(instance.board.id, msg_type, data)

@receiver(post_delete, sender=Note)
def note_deleted(sender, instance, **kwargs):
    broadcast_update(instance.board.id, 'NOTE_DELETED', {'id': str(instance.id)})

@receiver(post_save, sender=Upvote)
def upvote_added(sender, instance, created, **kwargs):
    # When an upvote happens, we need to update the NOTE
    if created:
        note = instance.note
        
        # --- GRAVITY PHYSICS ---
        # Pull the note 5% closer to the origin (0,0) per upvote
        # This naturally sorts popular ideas to the center
        GRAVITY_FACTOR = 0.95
        
        note.position_x = float(note.position_x) * GRAVITY_FACTOR
        note.position_y = float(note.position_y) * GRAVITY_FACTOR
        note.save() # This triggers 'note_saved' which broadcasts the update
        
        # We don't need to broadcast here because note.save() does it


@receiver(post_delete, sender=Upvote)
def upvote_removed(sender, instance, **kwargs):
    # Even on remove, we might want to "push" it back? 
    # For now, just broadcast the count change
    note = instance.note
    # Force a save to update timestamp or just trigger broadcast?
    # Simple save triggers broadcast
    note.save()

@receiver(post_save, sender=Board)
def board_saved(sender, instance, created, **kwargs):
    # Broadcast board updates (privacy toggle, title changes, etc.)
    from .serializers import BoardSerializer
    data = BoardSerializer(instance).data
    
    if not created and instance.is_soft_deleted:
        msg_type = 'BOARD_DELETED'
    else:
        msg_type = 'BOARD_CREATED' if created else 'BOARD_UPDATED'
        
    broadcast_update(instance.id, msg_type, data)

@receiver(post_save, sender=BoardInvite)
def board_invite_saved(sender, instance, created, **kwargs):
    """
    When an invite is created (either manually or via access request approval),
    broadcast to the board so the requester's UI can auto-refresh.
    """
    if created:
        broadcast_update(instance.board.id, 'ACCESS_GRANTED', {'email': instance.email})

@receiver(post_save, sender=AccessRequest)
def access_request_saved(sender, instance, created, **kwargs):
    """Notify when a request is rejected so the user can try again."""
    if not created and instance.status == 'REJECTED':
        broadcast_update(instance.board.id, 'ACCESS_REJECTED', {
            'email': instance.email,
            'ghost_id': str(instance.ghost.ghost_id)
        })
