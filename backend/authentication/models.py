from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserRole(models.TextChoices):
    AUDITOR = "AUDITOR", "Auditor"
    ADMIN = "ADMIN", "Administrator"
    # Agency Portal RBAC roles (Requirement 3.1)
    AGENCY_ADMIN = "AGENCY_ADMIN", "Agency Administrator"
    AGENCY_OFFICER = "AGENCY_OFFICER", "Agency Officer"
    REVIEWER = "REVIEWER", "Reviewer"
    GOVERNMENT_AUDITOR = "GOVERNMENT_AUDITOR", "Government Auditor"


class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, role=UserRole.AUDITOR, **extra_fields):
        if not username:
            raise ValueError("Username is required")
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,  # extended from 10 to accommodate new role names
        choices=UserRole.choices,
        default=UserRole.AUDITOR,
    )
    # Agency FK — null for internal users (AUDITOR, ADMIN)
    # Populated for agency-scoped roles (AGENCY_ADMIN, AGENCY_OFFICER, REVIEWER, GOVERNMENT_AUDITOR)
    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    email_verified = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "auth_user"

    def __str__(self):
        return f"{self.username} ({self.role})"

    def is_locked(self):
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def is_admin(self):
        return self.role == UserRole.ADMIN

    def is_auditor(self):
        return self.role == UserRole.AUDITOR


