import pytest
from identity.models import AnonymousProfile, User
import uuid

@pytest.mark.django_db
def test_anonymous_profile_creation():
    """Test that an AnonymousProfile can be created with a unique ghost_id."""
    profile = AnonymousProfile.objects.create()
    assert isinstance(profile.ghost_id, uuid.UUID)
    assert profile.is_pro is False
    assert profile.is_soft_deleted is False

@pytest.mark.django_db
def test_anonymous_profile_pro_upgrade():
    """Test that upgrading a profile to PRO works correctly."""
    profile = AnonymousProfile.objects.create()
    profile.is_pro = True
    profile.stripe_customer_id = "cus_test_123"
    profile.save()
    
    updated_profile = AnonymousProfile.objects.get(ghost_id=profile.ghost_id)
    assert updated_profile.is_pro is True
    assert updated_profile.stripe_customer_id == "cus_test_123"

@pytest.mark.django_db
def test_link_profile_to_user():
    """Test linking an anonymous profile to a registered user."""
    user = User.objects.create_user(email="test@example.com")
    profile = AnonymousProfile.objects.create(user=user)
    
    assert profile.user == user
    assert user.ghost_profile == profile
