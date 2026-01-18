from rest_framework import viewsets, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError

from ..models import Note, Upvote
from ..serializers import NoteSerializer
from identity.permissions import IsOwnerOrAdminToken
from .pagination import StandardResultsSetPagination


class NoteViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Note CRUD and upvoting.
    
    Custom Actions:
    - toggle_upvote: Upvote/unvote a note
    """
    queryset = Note.objects.all().order_by('-created_at')
    serializer_class = NoteSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsOwnerOrAdminToken]
    filter_backends = [filters.SearchFilter]
    search_fields = ['content']

    def get_queryset(self):
        from django.db.models import Q
        ghost = getattr(self.request, 'ghost', None)
        user = self.request.user
        
        # Base filter: Board must not be soft deleted
        q_filter = Q(board__is_soft_deleted=False)
        
        # Access logic:
        # 1. Board is public
        # 2. Board creator ghost matches current ghost
        # 3. Board owner matches current authenticated user
        # 4. Current user is invited to the board
        access_filter = Q(board__is_public=True)
        ghost = getattr(self.request, 'ghost', None)
        user = self.request.user
        admin_token = self.request.headers.get('X-Admin-Token')

        if ghost:
            access_filter |= Q(board__creator_ghost=ghost)
        if user.is_authenticated:
            access_filter |= Q(board__creator_ghost__user=user)
            access_filter |= Q(board__invites__email=user.email)
        if admin_token:
            access_filter |= Q(board__secret_admin_token=admin_token)
            
        queryset = Note.objects.filter(q_filter & access_filter).distinct().order_by('-created_at')
        
        board_id = self.request.query_params.get('board')
        if board_id:
            queryset = queryset.filter(board_id=board_id)
        return queryset

    def perform_create(self, serializer):
        ghost = getattr(self.request, 'ghost', None)
        if not ghost:
            raise ValidationError({"detail": "X-Ghost-ID header required."})
            
        board = serializer.validated_data['board']
        admin_token = self.request.headers.get('X-Admin-Token')
        is_admin = (board.creator_ghost == ghost) or (admin_token and str(board.secret_admin_token) == admin_token)

        if board.is_public or is_admin:
            serializer.save(creator_ghost=ghost)
        else:
            raise PermissionDenied("This board is private.")

    @action(detail=False, methods=['get'], url_path='created-by-me')
    def created_by_me(self, request):
        """Notes created by the current user (via Ghost ID linkage)."""
        ghost = getattr(request, 'ghost', None)
        user = request.user
        
        # We need to find notes created by either the current ghost OR the user's linked ghost
        # If user is authenticated, we trust their ghost_profile if it exists
        
        ghosts = []
        if ghost:
            ghosts.append(ghost)
        if user.is_authenticated and hasattr(user, 'ghost_profile') and user.ghost_profile:
            ghosts.append(user.ghost_profile)
            
        if not ghosts:
            return Response({"detail": "No identity found."}, status=status.HTTP_400_BAD_REQUEST)
            
        notes = Note.objects.filter(
            creator_ghost__in=ghosts,
            board__is_soft_deleted=False
        ).order_by('-created_at')

        # Manual search support for custom action
        search_query = request.query_params.get('search', None)
        if search_query:
            notes = notes.filter(content__icontains=search_query)
        
        page = self.paginate_queryset(notes)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], url_path='upvoted-by-me')
    def upvoted_by_me(self, request):
        """Notes upvoted by the current user."""
        ghost = getattr(request, 'ghost', None)
        user = request.user
        
        ghosts = []
        if ghost:
            ghosts.append(ghost)
        if user.is_authenticated and hasattr(user, 'ghost_profile') and user.ghost_profile:
            ghosts.append(user.ghost_profile)
            
        if not ghosts:
             return Response({"detail": "No identity found."}, status=status.HTTP_400_BAD_REQUEST)

        # distinct() is important if multiple ghosts map to same notes (unlikely but safe)
        notes = Note.objects.filter(
            upvotes__ghost__in=ghosts,
            board__is_soft_deleted=False
        ).distinct().order_by('-created_at')

        # Manual search support for custom action
        search_query = request.query_params.get('search', None)
        if search_query:
            notes = notes.filter(content__icontains=search_query)
        
        page = self.paginate_queryset(notes)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.AllowAny])
    def toggle_upvote(self, request, pk=None):
        """Toggle upvote on a note."""
        note = self.get_object()
        ghost = getattr(request, 'ghost', None)
        
        if not ghost:
            return Response({"detail": "Ghost ID required."}, status=status.HTTP_400_BAD_REQUEST)
        
        if note.creator_ghost == ghost:
            return Response({"detail": "Cannot upvote own note."}, status=status.HTTP_403_FORBIDDEN)
            
        upvote, created = Upvote.objects.get_or_create(note=note, ghost=ghost)
        if not created:
            upvote.delete()
            # Note: signal on delete will broadcast update
            return Response({'upvotes': note.upvote_count, 'action': 'unvoted'})
        
        # Note: signal on create will broadcast update
        return Response({'upvotes': note.upvote_count, 'action': 'upvoted'})
