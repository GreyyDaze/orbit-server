from rest_framework import permissions

class IsOwnerOrAdminToken(permissions.BasePermission):
    """
    Permission check for Orbit v2 using Ghost Identity.
    
    Allows access if:
    1. It's a SAFE_METHOD (GET/HEAD/OPTIONS)
    2. Request Ghost Identity matches the object's creator_ghost (Author)
    3. User is authenticated and matches the creator_ghost.user (Claimed ownership)
    4. Valid X-Admin-Token is provided (Master Link)
    
    This permission is generic and works with any model that has:
    - creator_ghost field (ForeignKey to AnonymousProfile)
    - board field (for nested objects like Note)
    - secret_admin_token field (on Board model)
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        from workspace.models import Board
        is_board = isinstance(obj, Board)
        target_board = obj if is_board else obj.board
        
        # 1. Author Checks (Highest Priority for Notes)
        # Allows authors to edit/delete/move their own notes regardless of admin restrictions
        if not is_board:
            # Personal Note Action (Author Rights)
            if request.ghost and obj.creator_ghost == request.ghost:
                return True
            # Authenticated Author Action (Linked Author)
            if request.user.is_authenticated and obj.creator_ghost.user == request.user:
                return True

        # 2. Board Admin/Owner Checks
        # For Board objects, admin/owner grants full access
        # For Note objects, admin/owner grants ONLY position updates (reorganize)
        
        has_admin_rights = False
        
        # Check Master Link (Token)
        admin_token = request.headers.get('X-Admin-Token') or request.META.get('HTTP_X_ADMIN_TOKEN')
        if admin_token and str(target_board.secret_admin_token).lower() == str(admin_token).lower():
            has_admin_rights = True
            
        # Check Claimed Ownership
        if request.user.is_authenticated and target_board.creator_ghost.user == request.user:
            has_admin_rights = True
            
        if has_admin_rights:
            if is_board:
                return True
            else:
                # Admin acting on someone else's note
                # ALLOW: Position updates (Drag/Reorganize)
                if request.method == 'PATCH':
                    data = request.data
                    allowed_fields = {'position_x', 'position_y'}
                    actual_fields = set(data.keys())
                    if actual_fields and actual_fields.issubset(allowed_fields):
                        return True
                # DENY: Deletion, Content Editing, Label Toggling on others' notes
                return False
            
        return False
