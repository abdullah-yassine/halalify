from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, apple_user_id, **extra_fields):
        if not apple_user_id:
            raise ValueError("apple_user_id is required")
        user = self.model(apple_user_id=apple_user_id, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, apple_user_id, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(apple_user_id, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    apple_user_id = models.CharField(max_length=255, unique=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "apple_user_id"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "accounts_user"
