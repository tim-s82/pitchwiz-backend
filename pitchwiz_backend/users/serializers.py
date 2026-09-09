from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


def validate_user_roles(value):
    if not isinstance(value, list):
        raise serializers.ValidationError("Roles must be a list.")
    valid_roles = [choice[0] for choice in User.Role.choices]
    for role in value:
        if role not in valid_roles:
            raise serializers.ValidationError(f"'{role}' is not a valid role.")
    if User.Role.EXTERNAL in value and len(value) > 1:
        raise serializers.ValidationError(
            "The External user role is mutually exclusive with all other roles."
        )
    return value


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "roles",
            "is_locked",
            "force_password_reset",
            "last_password_change",
        ]
        read_only_fields = ["last_password_change"]

    def validate_roles(self, value):
        return validate_user_roles(value)


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "roles",
        ]

    def validate_roles(self, value):
        return validate_user_roles(value)

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            roles=validated_data.get("roles", []),
        )
        user.set_password(validated_data["password"])
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
