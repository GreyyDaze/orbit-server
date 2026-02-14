import uuid
from django.db import models

class Board(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, default="Untitled Board")
    
    # Trace ownership to the identity app
    creator_ghost = models.ForeignKey('identity.AnonymousProfile', on_delete=models.CASCADE, related_name='boards')
    
    is_public = models.BooleanField(default=True)
    secret_admin_token = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_soft_deleted = models.BooleanField(default=False)
    soft_deleted_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_claimed(self):
        return self.creator_ghost.user is not None

    def __str__(self):
        return self.title

class Note(models.Model):
    class Colour(models.TextChoices):
        YELLOW = "YELLOW", "Yellow"
        CREATIVE = "CREATIVE", "Creative"
        COOL = "COOL", "Cool"
        FRESH = "FRESH", "Fresh"
        ROYAL = "ROYAL", "Royal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    board = models.ForeignKey(Board, related_name="notes", on_delete=models.CASCADE)
    creator_ghost = models.ForeignKey('identity.AnonymousProfile', on_delete=models.CASCADE, related_name='notes')
    
    content = models.TextField(blank=True)
    colour = models.CharField(max_length=20, choices=Colour.choices, default=Colour.YELLOW)
    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    is_anonymous_to_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def upvote_count(self):
        return self.upvotes.count()

    def __str__(self):
        return f"Note {str(self.id)[:8]}"

class Upvote(models.Model):
    note = models.ForeignKey(Note, related_name="upvotes", on_delete=models.CASCADE)
    ghost = models.ForeignKey('identity.AnonymousProfile', related_name="upvotes_cast", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('note', 'ghost')

class BoardInvite(models.Model):
    board = models.ForeignKey(Board, related_name="invites", on_delete=models.CASCADE)
    email = models.EmailField()
    invited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('board', 'email')

    def __str__(self):
        return f"{self.email} invited to {self.board.title}"

class AccessRequest(models.Model):
    board = models.ForeignKey(Board, related_name="access_requests", on_delete=models.CASCADE)
    ghost = models.ForeignKey('identity.AnonymousProfile', on_delete=models.CASCADE)
    email = models.EmailField(null=True, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='PENDING') # PENDING, APPROVED, REJECTED
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('board', 'ghost')

    def __str__(self):
        return f"Request for {self.board.title} from {self.ghost.ghost_id}"
