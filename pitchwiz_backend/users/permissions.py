from django.contrib.auth import get_user_model
from rest_framework.permissions import SAFE_METHODS, BasePermission

User = get_user_model()


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and User.Role.ADMIN in request.user.roles
        )


class IsUserManager(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                User.Role.ADMIN in request.user.roles
                or User.Role.USER_MANAGER in request.user.roles
            )
        )


class IsFixtureSecretary(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                User.Role.ADMIN in request.user.roles
                or User.Role.FIXTURE_SECRETARY in request.user.roles
            )
        )


class IsCaterer(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                User.Role.ADMIN in request.user.roles
                or User.Role.CATERER in request.user.roles
            )
        )


class IsTeamManager(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                User.Role.ADMIN in request.user.roles
                or User.Role.TEAM_MANAGER in request.user.roles
            )
        )


class IsAdminOrManagerOrSecretaryOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated

        return bool(
            request.user
            and request.user.is_authenticated
            and (
                User.Role.ADMIN in request.user.roles
                or User.Role.USER_MANAGER in request.user.roles
                or User.Role.FIXTURE_SECRETARY in request.user.roles
            )
        )


class IsExternal(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and User.Role.EXTERNAL in request.user.roles
        )


class IsBookingOwnerOrSecretary(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        if not (request.user and request.user.is_authenticated):
            return False

        if (
            User.Role.ADMIN in request.user.roles
            or User.Role.FIXTURE_SECRETARY in request.user.roles
        ):
            return True

        if User.Role.TEAM_MANAGER in request.user.roles:
            if obj.requested_by == request.user:
                return True
            if (
                obj.fixture
                and obj.fixture.team
                and obj.fixture.team.managers.filter(id=request.user.id).exists()
            ):
                return True

        return False


class IsFixtureManagerOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated

        return bool(
            request.user
            and request.user.is_authenticated
            and (
                User.Role.ADMIN in request.user.roles
                or User.Role.FIXTURE_SECRETARY in request.user.roles
                or User.Role.TEAM_MANAGER in request.user.roles
            )
        )


class IsGroundstaff(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (
                User.Role.ADMIN in request.user.roles
                or User.Role.GROUNDSTAFF in request.user.roles
            )
        )
