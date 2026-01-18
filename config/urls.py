from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Workspace APIs (Boards & Notes)
    path('api/v1/workspace/', include('workspace.urls')),
    
    # Identity APIs (Auth & Ghosts)
    path('api/v1/identity/', include('identity.urls')),
]
