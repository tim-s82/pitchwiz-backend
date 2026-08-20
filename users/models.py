from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        USER_MANAGER = "USER_MANAGER", "User Manager"
        TEAM_MANAGER = "TEAM_MANAGER", "Team Manager"
        FIXTURE_SECRETARY = "FIXTURE_SECRETARY", "Fixture Secretary"
        CATERER = "CATERER", "Caterer"
        EXTERNAL = "EXTERNAL", "External User"

    roles = models.JSONField(default=list, blank=True)
    last_password_change = models.DateTimeField(auto_now_add=True)
    force_password_reset = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Always add ADMIN role to superuser
        if self.is_superuser and self.Role.ADMIN not in self.roles:
            self.roles.append(self.Role.ADMIN)
        super().save(*args, **kwargs)
