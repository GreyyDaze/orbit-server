import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone

class UserManager(BaseUserManager):
    def create_user(self, email, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        extra_fields.setdefault("username", email)
        
        user = self.model(email=email, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

class AnonymousProfile(models.Model):
    """
    Ghost Identity - One per browser/device.
    
    Lifecycle:
    - Created when user first visits (or generates Ghost ID)
    - Linked to User account on signup (user field populated)
    - Soft-deleted 30 days after creation
    - Hard-deleted 7 days after soft-delete (37 days total)
    
    NO last_active field - prevents users from extending free tier indefinitely.
    """
    ghost_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='ghost_profile')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Retention tracking (30+7 day policy)
    is_soft_deleted = models.BooleanField(default=False)
    soft_deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Ghost ({str(self.ghost_id)[:8]})"

class VerificationCode(models.Model):
    email = models.EmailField()
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
