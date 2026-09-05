import logging
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsUserManager
from .serializers import ChangePasswordSerializer, UserCreateSerializer, UserSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("id")
    permission_classes = [IsUserManager]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    @action(detail=False, methods=["get", "put", "patch"], permission_classes=[])
    def me(self, request):
        if not request.user.is_authenticated:
            logger.warning("Unauthenticated access attempt to 'me' endpoint.")
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        if request.method == "GET":
            serializer = UserSerializer(request.user)
            return Response(serializer.data)
        
        elif request.method in ["PUT", "PATCH"]:
            # Only allow changing certain fields for 'me'
            serializer = UserSerializer(request.user, data=request.data, partial=True)
            if serializer.is_valid():
                # Prevent escalating privileges via 'me' endpoint
                if "roles" in serializer.validated_data:
                    logger.warning(
                        f"User {request.user.id} ({request.user.get_username()}) attempted "
                        "to modify roles via the 'me' endpoint."
                    )
                    serializer.validated_data.pop("roles")
                
                serializer.save()
                logger.info(f"User {request.user.id} ({request.user.get_username()}) updated their profile.")
                return Response(serializer.data)
            
            logger.warning(
                f"Profile update validation failed for user {request.user.id}: {serializer.errors}"
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChangePasswordView(APIView):
    permission_classes = [] # or IsAuthenticated if you handle auth globally/locally

    def post(self, request):
        if not request.user.is_authenticated:
            logger.warning("Unauthenticated access attempt to 'change_password' endpoint.")
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            if not request.user.check_password(serializer.validated_data["old_password"]):
                logger.warning(
                    f"Failed password change attempt for user {request.user.id} "
                    f"({request.user.get_username()}): incorrect current password provided."
                )
                return Response(
                    {"old_password": ["Wrong password."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            request.user.set_password(serializer.validated_data["new_password"])
            request.user.last_password_change = timezone.now()
            request.user.force_password_reset = False
            request.user.save()

            logger.info(f"Password successfully changed for user {request.user.id} ({request.user.get_username()}).")
            return Response({"status": "password set"}, status=status.HTTP_200_OK)

        logger.warning(f"Password change validation failed for user {request.user.id}: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)