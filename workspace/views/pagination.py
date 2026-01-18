from rest_framework import pagination


class StandardResultsSetPagination(pagination.LimitOffsetPagination):
    """Standard pagination for all workspace endpoints."""
    default_limit = 20
    max_limit = 1000  # Increased for spatial discovery

    def paginate_queryset(self, queryset, request, view=None):
        if request.query_params.get('paginate', 'true').lower() == 'false':
            return None
        return super().paginate_queryset(queryset, request, view)
