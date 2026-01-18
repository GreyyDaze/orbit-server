from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import GenerateGhostIDView, SendOTPView, VerifyOTPView, LogoutView, ProfileView, MigrateGhostDataView

urlpatterns = [
    # Ghost Identity
    path('ghost/generate/', GenerateGhostIDView.as_view(), name='generate_ghost'),
    path('ghost/migrate/', MigrateGhostDataView.as_view(), name='migrate_ghost_data'),
    
    # Identity Management
    path('otp-send/', SendOTPView.as_view(), name='otp_send'),
    path('otp-verify/', VerifyOTPView.as_view(), name='otp_verify'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', ProfileView.as_view(), name='profile'),
    
    # JWT Lifecycle
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
