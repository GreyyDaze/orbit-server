from rest_framework import serializers
from identity.serializers import UserSerializer
from .models import Board, Note, BoardInvite, AccessRequest

class BoardInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoardInvite
        fields = ['id', 'email', 'invited_at']

class AccessRequestSerializer(serializers.ModelSerializer):
    ghost_id = serializers.UUIDField(source='ghost.ghost_id', read_only=True)
    
    class Meta:
        model = AccessRequest
        fields = ['id', 'board', 'ghost_id', 'email', 'message', 'status', 'created_at']
        read_only_fields = ['id', 'board', 'ghost_id', 'status', 'created_at']

class NoteSerializer(serializers.ModelSerializer):
    upvotes = serializers.IntegerField(source='upvote_count', read_only=True)
    is_author = serializers.SerializerMethodField()
    is_upvoted = serializers.SerializerMethodField()
    author_label = serializers.SerializerMethodField()
    
    class Meta:
        model = Note
        fields = [
            'id', 'board', 'content', 'colour', 
            'position_x', 'position_y', 'upvotes', 
            'creator_ghost', 'created_at', 'is_author', 'is_upvoted',
            'is_anonymous_to_public', 'author_label'
        ]
        read_only_fields = ['upvotes', 'creator_ghost', 'created_at', 'author_label']

    def get_is_author(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        ghost = getattr(request, 'ghost', None)
        return obj.creator_ghost == ghost

    def get_is_upvoted(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        ghost = getattr(request, 'ghost', None)
        if not ghost:
            return False
        return obj.upvotes.filter(ghost=ghost).exists()

    def get_author_label(self, obj):
        # If set to anonymous, return the ID hash
        if obj.is_anonymous_to_public:
            return f"#{str(obj.id)[:4]}"
        
        # If public, check if it's the board owner
        # We need to access the board's creator
        # Optimization: obj.board is a foreign key, so obj.board.creator_ghost might hit DB
        # But we can assume creator_ghost matches for the "Admin" feature to be valid
        
        board_owner_ghost = obj.board.creator_ghost
        if obj.creator_ghost == board_owner_ghost:
            user = board_owner_ghost.user
            if user:
                return f"ADMIN ({user.username})"
            return "ADMIN"
            
        # Fallback if a non-owner somehow managed to set this flag (should be prevented by permission logic if strict, 
        # but for viewing representation we fallback to anonymous-like or just their ID)
        return f"#{str(obj.id)[:4]}"

class BoardSerializer(serializers.ModelSerializer):
    notes = NoteSerializer(many=True, read_only=True)
    owner = UserSerializer(source='creator_ghost.user', read_only=True)
    is_admin = serializers.SerializerMethodField()
    is_claimed = serializers.SerializerMethodField()
    note_count = serializers.SerializerMethodField()
    invites = BoardInviteSerializer(many=True, read_only=True)

    class Meta:
        model = Board
        fields = [
            "id", "title", "notes", "owner", 
            "is_claimed", "is_public", "is_admin",
            "created_at", "note_count", "invites"
        ]
        read_only_fields = ["is_claimed", "note_count"]

    def get_is_admin(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        
        ghost = getattr(request, 'ghost', None)
        admin_token = request.headers.get('X-Admin-Token')
        
        is_ghost_owner = obj.creator_ghost == ghost
        is_token_owner = admin_token and str(obj.secret_admin_token) == admin_token
        is_user_owner = (obj.creator_ghost.user == request.user and request.user.is_authenticated)
        
        return is_ghost_owner or is_token_owner or is_user_owner
    
    def get_is_claimed(self, obj):
        return obj.is_claimed
    
    def get_note_count(self, obj):
        return obj.notes.count()

class BoardDiscoverySerializer(serializers.ModelSerializer):
    """Lightweight serializer for discovery gallery"""
    note_count = serializers.IntegerField(read_only=True)
    total_upvotes = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Board
        fields = ['id', 'title', 'created_at', 'note_count', 'total_upvotes']

class BoardClaimSerializer(serializers.Serializer):
    """Serializer for claiming a board"""
    pass  # No input needed, uses request.user and request.ghost

class BoardRevokeLinkSerializer(serializers.Serializer):
    """Serializer for revoking admin link"""
    new_admin_token = serializers.UUIDField(read_only=True)