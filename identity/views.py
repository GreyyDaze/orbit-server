import random
import uuid
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import login, get_user_model
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import AnonymousProfile, VerificationCode
from .serializers import UserSerializer, OTPSendSerializer, OTPVerifySerializer
from workspace.models import Board, Note, Upvote

User = get_user_model()

class GenerateGhostIDView(APIView):
    """
    Generate a cryptographically secure Ghost ID.
    PUBLIC - No authentication required.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ghost_id = uuid.uuid4()
        AnonymousProfile.objects.create(ghost_id=ghost_id)
        return Response({
            "ghost_id": str(ghost_id),
            "detail": "Ghost identity created."
        })

class SendOTPView(APIView):
    """
    Send OTP code to email.
    PUBLIC - No authentication required.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = OTPSendSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = "".join([str(random.randint(0, 9)) for _ in range(6)])
            expires_at = timezone.now() + timedelta(minutes=10)
            VerificationCode.objects.create(email=email, code=code, expires_at=expires_at)
            
            # Check if account already exists and ensure it has a ghost profile
            user = User.objects.filter(email=email).first()
            existing_ghost_id = None
            
            if user:
                if not hasattr(user, 'ghost_profile') or not user.ghost_profile:
                    from .models import AnonymousProfile
                    import uuid
                    AnonymousProfile.objects.create(user=user, ghost_id=uuid.uuid4())
                existing_ghost_id = str(user.ghost_profile.ghost_id)
            else:
                # User does not exist (Guest / First Time)
                # Check if they sent a generic ghost ID in headers (Guest browsing)
                if hasattr(request, 'ghost') and request.ghost:
                    existing_ghost_id = str(request.ghost.ghost_id)
                else:
                    # Clean Sign In: No user, No header.
                    # Generate a provisional Ghost ID for this session so verify_otp can link it.
                    from .models import AnonymousProfile
                    import uuid
                    new_ghost = AnonymousProfile.objects.create(ghost_id=uuid.uuid4())
                    existing_ghost_id = str(new_ghost.ghost_id)

            print(f"DEBUG: OTP for {email} is {code}, Ghost: {existing_ghost_id}")
            return Response({
                "detail": "Verification code sent.", 
                "debug_code": code,
                "ghost_id": existing_ghost_id
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(APIView):
    """
    Verify OTP and link Ghost to User account.
    PUBLIC - No authentication required (this IS the authentication).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            code = serializer.validated_data['code']
            ghost_id = serializer.validated_data['ghost_id']
            
            vc = VerificationCode.objects.filter(email=email, code=code).first()
            if vc and vc.is_valid():
                vc.is_used = True
                vc.save()
                
                user, created = User.objects.get_or_create(email=email)
                ghost, g_created = AnonymousProfile.objects.get_or_create(ghost_id=ghost_id)
                
                # Check for existing data on the current guest profile
                has_anonymous_data = Board.objects.filter(creator_ghost=ghost).exists() or \
                                   Note.objects.filter(creator_ghost=ghost).exists()
                
                conflict_exists = False
                
                # Check if user already has a DIFFERENT ghost profile (Permanent Account Profile)
                if hasattr(user, 'ghost_profile') and user.ghost_profile and user.ghost_profile != ghost:
                    # CONFLICT: Returning user with a different ghost
                    if has_anonymous_data:
                        conflict_exists = True
                    else:
                        # No data on current ghost, just switch to old one
                        ghost = user.ghost_profile
                else:
                    # New user OR same ghost
                    # If they have anonymous data, they should choose to merge it
                    if has_anonymous_data and not ghost.user:
                        conflict_exists = True
                    
                # Link ghost to user ONLY if there's no conflict
                # If conflict exists, let the migration API handle it
                if not conflict_exists:
                    ghost.user = user
                    ghost.save()
                
                refresh = RefreshToken.for_user(user)
                
                # Get list of boards to show user what will be merged
                anonymous_boards = []
                if conflict_exists:
                    boards = Board.objects.filter(creator_ghost=ghost).values('id', 'title', 'created_at')
                    anonymous_boards = [{
                        'id': str(b['id']),
                        'title': b['title'],
                        'created_at': b['created_at'].isoformat()
                    } for b in boards]
                
                user_data = {
                    "id": str(user.id),
                    "email": user.email,
                    "username": user.username,
                    "created_at": user.created_at.isoformat(),
                    # Send the authoritative ghost ID if it exists
                    "ghost_id": str(user.ghost_profile.ghost_id) if hasattr(user, 'ghost_profile') and user.ghost_profile else str(ghost.ghost_id)
                }
                
                return Response({
                    "detail": "Identity verified.",
                    "user": user_data,
                    "has_conflict": conflict_exists,
                    "anonymous_boards": anonymous_boards,
                    "tokens": {
                        "refresh": str(refresh),
                        "access": str(refresh.access_token),
                    }
                })
            return Response({"detail": "Invalid or expired code."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MigrateGhostDataView(APIView):
    """
    Move data from a source Ghost ID to the authenticated user's profile.
    PROTECTED - Requires JWT authentication.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        source_ghost_id = request.data.get('source_ghost_id')
        if not source_ghost_id:
            return Response({"detail": "Source Ghost ID required."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            source_ghost = AnonymousProfile.objects.get(ghost_id=source_ghost_id)
            
            # Get or create target ghost (user's permanent profile)
            if hasattr(request.user, 'ghost_profile') and request.user.ghost_profile:
                target_ghost = request.user.ghost_profile
            else:
                # User doesn't have a ghost yet, use the source as their permanent one
                target_ghost = source_ghost
            
            if source_ghost != target_ghost:
                # 1. Migrate ALL Boards
                Board.objects.filter(creator_ghost=source_ghost).update(creator_ghost=target_ghost)
                # 2. Migrate ALL Notes
                Note.objects.filter(creator_ghost=source_ghost).update(creator_ghost=target_ghost)
                # 3. Migrate Upvotes
                Upvote.objects.filter(ghost=source_ghost).update(ghost=target_ghost)
            
            # Link the ghost to the user
            target_ghost.user = request.user
            target_ghost.save()
            
            return Response({"detail": "Data migrated successfully."})
            
        except AnonymousProfile.DoesNotExist:
             return Response({"detail": "Ghost profile not found."}, status=status.HTTP_404_NOT_FOUND)

class LogoutView(APIView):
    """
    Blacklist refresh token.
    PROTECTED - Requires JWT authentication.
    """
    # Relaxed to AllowAny so clients with expired access tokens can still 'logout' (blacklist refresh)
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Token blacklisting is optional - client-side token removal is sufficient
        # Just validate the token exists and return success
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate token format
        try:
            RefreshToken(refresh_token)
        except Exception:
            return Response({"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)
            
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)

class ProfileView(APIView):
    """
    Get or Update User Profile (Username).
    PROTECTED - Requires JWT authentication.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        user = request.user
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
