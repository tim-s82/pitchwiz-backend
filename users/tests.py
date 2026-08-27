from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.exceptions import ValidationError as DRFValidationError

from users.serializers import UserCreateSerializer, UserSerializer

User = get_user_model()


class UserRoleValidationTests(TestCase):
    def test_create_valid_team_manager(self):
        user = User(
            username="manager1",
            email="manager1@example.com",
            roles=[User.Role.TEAM_MANAGER],
        )
        user.set_password("Password123!")
        user.full_clean()
        user.save()
        self.assertEqual(user.roles, [User.Role.TEAM_MANAGER])

    def test_create_valid_external_user(self):
        user = User(
            username="dorsetcricket",
            email="dorset@example.com",
            roles=[User.Role.EXTERNAL],
        )
        user.set_password("Password123!")
        user.full_clean()
        user.save()
        self.assertEqual(user.roles, [User.Role.EXTERNAL])

    def test_invalid_role_raises_error(self):
        user = User(
            username="badrole",
            roles=["INVALID_ROLE_NAME"],
        )
        user.set_password("Password123!")
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_external_mutual_exclusivity_raises_error_on_model(self):
        user = User(
            username="mixeduser",
            roles=[User.Role.EXTERNAL, User.Role.TEAM_MANAGER],
        )
        user.set_password("Password123!")
        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()
        self.assertIn(
            "The External user role is mutually exclusive with all other roles.",
            str(ctx.exception),
        )

    def test_serializer_validation_passes_valid(self):
        data = {
            "username": "ser_external",
            "password": "Password123!",
            "roles": [User.Role.EXTERNAL],
        }
        serializer = UserCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(user.roles, [User.Role.EXTERNAL])

    def test_serializer_validation_fails_mixed_roles(self):
        data = {
            "username": "ser_mixed",
            "password": "Password123!",
            "roles": [User.Role.EXTERNAL, User.Role.CATERER],
        }
        serializer = UserCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("roles", serializer.errors)
        self.assertEqual(
            serializer.errors["roles"][0],
            "The External user role is mutually exclusive with all other roles.",
        )

    def test_serializer_validation_fails_invalid_roles(self):
        data = {
            "username": "ser_bad",
            "password": "Password123!",
            "roles": ["GARBAGE"],
        }
        serializer = UserCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("roles", serializer.errors)
        self.assertEqual(
            serializer.errors["roles"][0], "'GARBAGE' is not a valid role."
        )
