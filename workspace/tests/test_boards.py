import pytest
from rest_framework.test import APIClient
from identity.models import AnonymousProfile
from workspace.models import Board

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def ghost_profile():
    return AnonymousProfile.objects.create()

@pytest.mark.django_db
def test_create_board_limit_free_user(api_client, ghost_profile):
    """Test that a free user is limited to 2 active boards."""
    ghost_id = str(ghost_profile.ghost_id)
    
    # Create first board
    response = api_client.post('/api/v1/workspace/boards/', 
                                {'title': 'Board 1'}, 
                                HTTP_X_GHOST_ID=ghost_id)
    assert response.status_code == 201
    
    # Create second board
    response = api_client.post('/api/v1/workspace/boards/', 
                                {'title': 'Board 2'}, 
                                HTTP_X_GHOST_ID=ghost_id)
    assert response.status_code == 201
    
    # Attempt third board
    response = api_client.post('/api/v1/workspace/boards/', 
                                {'title': 'Board 3'}, 
                                HTTP_X_GHOST_ID=ghost_id)
    assert response.status_code == 400
    assert response.data['code'] == 'limit_reached'
    assert Board.objects.filter(creator_ghost=ghost_profile).count() == 2

@pytest.mark.django_db
def test_create_board_unlimited_pro_user(api_client, ghost_profile):
    """Test that a PRO user can create more than 2 boards."""
    ghost_profile.is_pro = True
    ghost_profile.save()
    ghost_id = str(ghost_profile.ghost_id)
    
    # Create 3 boards
    for i in range(3):
        response = api_client.post('/api/v1/workspace/boards/', 
                                    {'title': f'Board {i}'}, 
                                    HTTP_X_GHOST_ID=ghost_id)
        assert response.status_code == 201
        
    assert Board.objects.filter(creator_ghost=ghost_profile).count() == 3
