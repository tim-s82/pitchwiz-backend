from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.utils import timezone
from .serializers import UserSerializer, UserCreateSerializer, ChangePasswordSerializer
from .permissions import IsUserManager

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
                    serializer.validated_data.pop("roles")
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], permission_classes=[])
    def change_password(self, request):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            if not request.user.check_password(
                serializer.validated_data["old_password"]
            ):
                return Response(
                    {"old_password": ["Wrong password."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            request.user.set_password(serializer.validated_data["new_password"])
            request.user.last_password_change = timezone.now()
            request.user.force_password_reset = False
            request.user.save()
            return Response({"status": "password set"}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
