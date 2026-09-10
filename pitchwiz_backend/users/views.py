import logging

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from users.permissions import IsUserManager
from users.serializers import (
    ChangePasswordSerializer,
    UserCreateSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("id")
    permission_classes = [IsUserManager]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    @action(detail=False, methods=["get", "put", "patch"], permission_classes=[IsAuthenticated])
    def me(self, request):
        if request.method == "GET":
            serializer = UserSerializer(request.user)
            return Response(serializer.data)

        # Only allow changing certain fields for 'me'
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            # Prevent escalating privileges via 'me' endpoint
            if "roles" in serializer.validated_data:
                logger.warning(
                    "User %s (%s) attempted to modify roles via the 'me' endpoint.",
                    request.user.id,
                    request.user.get_username(),
                )
                serializer.validated_data.pop("roles")

            serializer.save()
            logger.info(
                "User %s (%s) updated their profile.",
                request.user.id,
                request.user.get_username(),
            )
            return Response(serializer.data)

        logger.warning(
            "Profile update validation failed for user %s: %s",
            request.user.id,
            serializer.errors,
        )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            if not request.user.check_password(serializer.validated_data["old_password"]):
                logger.warning(
                    "Failed password change attempt for user %s (%s): incorrect current password provided.",
                    request.user.id,
                    request.user.get_username(),
                )
                return Response(
                    {"old_password": ["Wrong password."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            request.user.set_password(serializer.validated_data["new_password"])
            request.user.last_password_change = timezone.now()
            request.user.force_password_reset = False
            request.user.save()

            logger.info(
                "Password successfully changed for user %s (%s).",
                request.user.id,
                request.user.get_username(),
            )
            return Response({"status": "password set"}, status=status.HTTP_200_OK)

        logger.warning(
            "Password change validation failed for user %s: %s",
            request.user.id,
            serializer.errors,
        )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
