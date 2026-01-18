from django.db.models import Q, Count, Sum
from django.db.models.functions import Coalesce
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication
import uuid

from ..models import Board, BoardInvite
from ..serializers import BoardSerializer, BoardDiscoverySerializer, BoardInviteSerializer
from identity.permissions import IsOwnerOrAdminToken
from .pagination import StandardResultsSetPagination


class BoardViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Board CRUD and ownership management.
    
    Custom Actions:
    - discover: Public gallery
    - my_boards: User's owned boards
    - history: Ghost's board history
    - claim: Claim anonymous board
    - revoke_link: Regenerate admin token
    """
    serializer_class = BoardSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        """
        Instantiate and return the list of permissions that this view requires.
        - detail=True actions (update, partial_update, delete, claim, revoke_link) 
          require the custom IsOwnerOrAdminToken check.
        - detail=False actions (list, create, discover, my_boards, history, check_permissions) 
          use the global AllowAny or handle it internally.
        """
        if self.action in ['update', 'partial_update', 'destroy', 'claim', 'revoke_link', 'invite']:
            return [IsOwnerOrAdminToken()]
        return super().get_permissions()

    # Optimized queryset
    def get_queryset(self):
        ghost = getattr(self.request, 'ghost', None)
        q_filter = Q(is_public=True, is_soft_deleted=False)
        
        if ghost:
            q_filter |= Q(creator_ghost=ghost)
        if self.request.user.is_authenticated:
            q_filter |= Q(creator_ghost__user=self.request.user)
            # Also include boards where user is invited
            q_filter |= Q(invites__email=self.request.user.email)
            
        return Board.objects.filter(q_filter).distinct().order_by('-created_at')

    def destroy(self, request, *args, **kwargs):
        """Soft delete the board."""
        from django.utils import timezone
        instance = self.get_object()
        instance.is_soft_deleted = True
        instance.soft_deleted_at = timezone.now()
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def retrieve(self, request, *args, **kwargs):
        """
        Override retrieve to handle PRIVATE boards with 403 instead of 404.
        """
        try:
            return super().retrieve(request, *args, **kwargs)
        except Exception:
            # If not found in the filtered queryset, check if it exists at all
            pk = kwargs.get('pk')
            try:
                board = Board.objects.get(pk=pk, is_soft_deleted=False)
                
                # If we are here, it means the board exists but was filtered out (likely due to Privacy)
                if not board.is_public:
                    user = request.user
                    ghost = getattr(request, 'ghost', None)
                    
                    # Double check permissions (Owner or Invited)
                    is_owner = (user.is_authenticated and board.creator_ghost.user == user) or \
                               (ghost and board.creator_ghost == ghost)
                    is_invited = user.is_authenticated and board.invites.filter(email=user.email).exists()
                    
                    if is_owner or is_invited:
                        # User has access, but for some reason wasn't in the queryset.
                        # (e.g. if authentication middleware failed but token is valid)
                        # Returning manually is a safe fallback.
                        serializer = self.get_serializer(board)
                        return Response(serializer.data)
                        
                    return Response(
                        {"detail": "This board is private.", "code": "private_board"}, 
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                # If it's public but still failed super.retrieve, it might be a genuine 404
                return Response({"detail": "Board not found."}, status=status.HTTP_404_NOT_FOUND)
                
            except Board.DoesNotExist:
                return Response({"detail": "Board not found."}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                # Unexpected error fallback
                return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Return the created board along with the secret token (FOR ONE TIME COPY)
        board = serializer.instance
        return Response({
            "board": BoardSerializer(board, context={'request': request}).data,
            "secret_admin_token": str(board.secret_admin_token)
        }, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        if not getattr(self.request, 'ghost', None):
            raise ValidationError({"detail": "X-Ghost-ID header required."})
        serializer.save(creator_ghost=self.request.ghost)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def discover(self, request):
        """Public board discovery gallery."""
        boards = Board.objects.filter(
            is_public=True,
            is_soft_deleted=False
        ).annotate(
            note_count=Count('notes'),
            total_upvotes=Coalesce(Sum('notes__upvotes'), 0)
        )
        
        sort_by = request.query_params.get('sort', 'recent')
        if sort_by == 'popular':
            boards = boards.order_by('-total_upvotes', '-created_at')
        else:
            boards = boards.order_by('-created_at')

        search = request.query_params.get('search')
        if search:
            boards = boards.filter(
                Q(title__icontains=search) | 
                Q(notes__content__icontains=search)
            ).distinct()
        
        page = self.paginate_queryset(boards)
        serializer = BoardDiscoverySerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], url_path='my-boards', 
            authentication_classes=[JWTAuthentication],
            permission_classes=[permissions.IsAuthenticated])
    def my_boards(self, request):
        """User's owned boards (claimed only)."""
        boards = Board.objects.filter(
            creator_ghost__user=request.user
        ).annotate(
            note_count=Count('notes')
        ).order_by('-created_at')
        
        page = self.paginate_queryset(boards)
        serializer = BoardSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], url_path='invited', 
            authentication_classes=[JWTAuthentication],
            permission_classes=[permissions.IsAuthenticated])
    def invited(self, request):
        """Boards the user is explicitly invited to via email."""
        boards = Board.objects.filter(
            invites__email=request.user.email
        ).annotate(
            note_count=Count('notes')
        ).order_by('-created_at')
        
        page = self.paginate_queryset(boards)
        serializer = BoardSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def history(self, request):
        """Ghost's board history (all boards created by this Ghost)."""
        ghost = getattr(request, 'ghost', None)
        if not ghost:
            return Response({"detail": "X-Ghost-ID header required."}, status=status.HTTP_400_BAD_REQUEST)
        
        boards = Board.objects.filter(
            creator_ghost=ghost
        ).annotate(
            note_count=Count('notes')
        ).order_by('-created_at')
        
        page = self.paginate_queryset(boards)
        serializer = BoardSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['post'], authentication_classes=[JWTAuthentication], permission_classes=[permissions.IsAuthenticated])
    def claim(self, request, pk=None):
        """Claim an anonymous board."""
        board = self.get_object()
        ghost = getattr(request, 'ghost', None)
        
        # Permission: Either matching Ghost ID OR possessing the valid Admin Master Token
        token_header = request.headers.get('X-Admin-Token')
        is_token_match = token_header and str(board.secret_admin_token) == token_header
        
        if not (ghost and board.creator_ghost == ghost) and not is_token_match:
            raise PermissionDenied("You can only claim boards you created or have the master key for.")
        
        # Check if ALREADY claimed by a DIFFERENT user
        if board.is_claimed:
            if board.creator_ghost.user == request.user:
                return Response({"detail": "You already own this board."}, status=status.HTTP_200_OK)
            return Response({"detail": "Board is already claimed by another user."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Link current ghost to the user if not already linked
        if not ghost.user:
            ghost.user = request.user
            ghost.save()
        elif ghost.user != request.user:
            # This should be impossible due to 1:1, but worth guarding
            return Response({"detail": "Identity conflict. Please sign in again."}, status=status.HTTP_400_BAD_REQUEST)

        # Transfer board to the current authenticated ghost
        if board.creator_ghost != ghost:
            board.creator_ghost = ghost
            board.save()
        
        return Response({
            "detail": "Board claimed successfully.",
            "board": BoardSerializer(board, context={'request': request}).data
        })

    @action(detail=False, methods=['get'])
    def check_permissions(self, request):
        """
        Check if the current Ghost/User/Token has admin rights.
        Requires ?board=UUID query parameter.
        """
        board_id = request.query_params.get('board')
        if not board_id:
            return Response({"detail": "Board ID required."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            board = Board.objects.get(id=board_id, is_soft_deleted=False)
        except (Board.DoesNotExist, ValidationError):
            return Response({"detail": "Board not found."}, status=status.HTTP_404_NOT_FOUND)
            
        admin_token = request.headers.get('X-Admin-Token')
        
        # 1. Admin Token Check (Flexibility for other browsers)
        is_token_match = admin_token and str(board.secret_admin_token) == admin_token
        
        # 2. Ownership Check (Ghost Identity or Claimed User)
        is_owner = False
        if request.user.is_authenticated and board.creator_ghost.user == request.user:
            is_owner = True
        elif hasattr(request, 'ghost') and request.ghost and board.creator_ghost == request.ghost:
            is_owner = True
            
        return Response({
            "is_admin": is_owner or is_token_match,
            "is_owner": is_owner
        })

    @action(detail=True, methods=['post', 'delete'], url_path='invite')
    def invite(self, request, pk=None):
        """Add or remove an invite for an email address."""
        board = self.get_object()
        email = request.data.get('email')
        
        if not email:
            return Response({"detail": "Email required."}, status=status.HTTP_400_BAD_REQUEST)
            
        if request.method == 'POST':
            invite_obj, created = BoardInvite.objects.get_or_create(board=board, email=email)
            return Response(BoardInviteSerializer(invite_obj).data, status=status.HTTP_201_CREATED)
        else:
            BoardInvite.objects.filter(board=board, email=email).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
