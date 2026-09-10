from django.urls import include, path
from rest_framework.routers import DefaultRouter
from users.views import ChangePasswordView

from .views import UserViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"users", UserViewSet, basename="user")

urlpatterns = [
    path("users/change-password", ChangePasswordView.as_view(), name="change-password"),
    path("", include(router.urls)),
]
