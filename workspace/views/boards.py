from django.db.models import Q, Count, Sum
from django.db.models.functions import Coalesce
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication
import uuid

from ..models import Board, BoardInvite, AccessRequest
from ..serializers import BoardSerializer, BoardDiscoverySerializer, BoardInviteSerializer, AccessRequestSerializer
from identity.models import AnonymousProfile
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
    - request_access: User requests access to a private board
    - access_requests: Admin views/manages requests
    """
    serializer_class = BoardSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        """
        Instantiate and return the list of permissions that this view requires.
        - detail=True actions (update, partial_update, delete, claim, revoke_link, invite) 
          require the custom IsOwnerOrAdminToken check.
        - detail=False actions (list, create, discover, my_boards, history, check_permissions) 
          use the global AllowAny or handle it internally.
        """
        if self.action in ['update', 'partial_update', 'destroy', 'claim', 'revoke_link', 'invite', 'access_requests']:
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
        pk = kwargs.get('pk')
        try:
            # First check if the board exists at all (including soft deleted check)
            board = Board.objects.get(pk=pk, is_soft_deleted=False)
            
            # If it's public, or we have access to it, use standard behavior
            if board.is_public:
                return super().retrieve(request, *args, **kwargs)
            
            # Handle Private Access Check
            user = request.user
            ghost = getattr(request, 'ghost', None)
            
            is_owner = (user.is_authenticated and board.creator_ghost.user == user) or \
                       (ghost and board.creator_ghost == ghost)
            is_invited = user.is_authenticated and board.invites.filter(email=user.email).exists()
            admin_token = request.headers.get('X-Admin-Token')
            is_token_match = admin_token and str(board.secret_admin_token) == admin_token

            if is_owner or is_invited or is_token_match:
                # User has right to see the private board
                serializer = self.get_serializer(board)
                return Response(serializer.data)
                
            # If not authorized, return 403 with specific code
            return Response(
                {"detail": "This board is private.", "code": "private_board"}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        except (Board.DoesNotExist, ValidationError):
            return Response(
                {"detail": "Board not found.", "code": "board_not_found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
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

    @action(detail=True, methods=['post'], url_path='request-access')
    def request_access(self, request, pk=None):
        """Submit an access request to a private board."""
        board = Board.objects.get(pk=pk, is_soft_deleted=False)
        ghost = getattr(request, 'ghost', None)
        
        if not ghost:
            return Response({"detail": "X-Ghost-ID header required."}, status=status.HTTP_400_BAD_REQUEST)
            
        email = request.data.get('email')
        message = request.data.get('message', '')
        
        # Prevent spamming duplicate requests
        q_dupe = Q(board=board) & (Q(ghost=ghost) | (Q(email=email) if email else Q(pk=None)))
        existing = AccessRequest.objects.filter(q_dupe).first()
        
        if existing:
            if existing.status == 'REJECTED':
                existing.status = 'PENDING'
                existing.message = message
                existing.email = email
                existing.save()
                return Response({"detail": "Request resubmitted."}, status=status.HTTP_201_CREATED)
            return Response({"detail": "Access request already submitted."}, status=status.HTTP_400_BAD_REQUEST)
            
        AccessRequest.objects.create(
            board=board,
            ghost=ghost,
            email=email,
            message=message
        )
        
        return Response({"detail": "Request submitted."}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'patch'], url_path='access-requests')
    def access_requests(self, request, pk=None):
        """Admin views and manages access requests."""
        board = self.get_object() # IsOwnerOrAdminToken handles this
        
        if request.method == 'GET':
            requests = board.access_requests.filter(status='PENDING').order_by('-created_at')
            serializer = AccessRequestSerializer(requests, many=True)
            return Response(serializer.data)
            
        # PATCH - Approve or Reject
        request_id = request.data.get('request_id')
        new_status = request.data.get('status') # APPROVED or REJECTED
        
        if not request_id or new_status not in ['APPROVED', 'REJECTED']:
            return Response({"detail": "request_id and valid status required."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            req_obj = AccessRequest.objects.get(id=request_id, board=board)
            req_obj.status = new_status
            req_obj.save()
            
            if new_status == 'APPROVED' and req_obj.email:
                # Add to BoardInvite if they provided an email
                BoardInvite.objects.get_or_create(board=board, email=req_obj.email)
            
            return Response({"detail": f"Request {new_status.lower()}."})
        except AccessRequest.DoesNotExist:
            return Response({"detail": "Request not found."}, status=status.HTTP_404_NOT_FOUND)

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
        
        # Authenticated user's permanent ghost
        user_ghost = getattr(request.user, 'ghost_profile', None)
        
        # Scenario A: The ghost we are using is NOT linked to a user yet.
        if not ghost.user:
            if user_ghost:
                # User already has a permanent ghost. We can't link this one too.
                # Instead, we'll transfer the board ownership to their permanent ghost.
                ghost = user_ghost
            else:
                # User has no ghost yet. Link this one to them.
                ghost.user = request.user
                ghost.save()
        elif ghost.user != request.user:
            # Identity conflict. Current ghost belongs to someone else.
            if is_token_match:
                # If they have the Master Key, we allow the transfer anyway
                # by moving it to the user's permanent ghost.
                if user_ghost:
                    ghost = user_ghost
                else:
                    # If user has no ghost, we could create one or link this one? 
                    # But if this ghost is already owned (ghost.user != request.user), 
                    # we can't link it to request.user due to 1:1.
                    # We'll just generate a new permanent ghost for the user.
                    ghost = AnonymousProfile.objects.create(user=request.user, ghost_id=uuid.uuid4())
            else:
                return Response({"detail": "Identity conflict. This identity belongs to another user."}, status=status.HTTP_400_BAD_REQUEST)

        # Transfer board to the target ghost (either linked or permanent user ghost)
        if board.creator_ghost != ghost:
            board.creator_ghost = ghost
            board.save()
        
        return Response({
            "detail": "Board claimed successfully.",
            "board": BoardSerializer(board, context={'request': request}).data
        })

    @action(detail=True, methods=['post'], url_path='revoke-link')
    def revoke_link(self, request, pk=None):
        """Regenerate the secret admin token for the board."""
        board = self.get_object()
        board.secret_admin_token = uuid.uuid4()
        board.save()
        return Response({
            "detail": "Admin link revoked and regenerated.",
            "new_admin_token": str(board.secret_admin_token)
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
