from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BoardViewSet, NoteViewSet

router = DefaultRouter()
router.register(r'boards', BoardViewSet, basename='board')
router.register(r'notes', NoteViewSet, basename='note')

urlpatterns = [
    path('', include(router.urls)),
]
