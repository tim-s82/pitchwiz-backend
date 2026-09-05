from users.views import ChangePasswordView
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import UserViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r"users", UserViewSet, basename="user")

urlpatterns = [
    path("", include(router.urls)),
    path("users/change-password", ChangePasswordView.as_view(), name="change-password"),
]
