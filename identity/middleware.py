from django.utils import timezone
from .models import AnonymousProfile

class GhostIdentityMiddleware:
    """
    Middleware to automatically extract Ghost ID from headers 
    and attach the AnonymousProfile to the request object.
    
    NOTE: Does NOT update last_active - Ghost IDs expire based on 
    created_at only (30 days from creation, no extensions).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ghost_id = request.headers.get('X-Ghost-ID')
        request.ghost = None

        if ghost_id:
            try:
                # Use get_or_create to handle any race conditions or missing profiles
                # as long as the ID is a valid string/UUID.
                profile, _ = AnonymousProfile.objects.get_or_create(ghost_id=ghost_id)
                request.ghost = profile
            except Exception:
                pass

        response = self.get_response(request)
        return response
