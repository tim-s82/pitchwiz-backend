from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.contrib.auth import get_user_model

User = get_user_model()

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and User.Role.ADMIN in request.user.roles)

class IsUserManager(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            User.Role.ADMIN in request.user.roles or 
            User.Role.USER_MANAGER in request.user.roles
        ))

class IsFixtureSecretary(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            User.Role.ADMIN in request.user.roles or 
            User.Role.FIXTURE_SECRETARY in request.user.roles
        ))

class IsCaterer(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            User.Role.ADMIN in request.user.roles or 
            User.Role.CATERER in request.user.roles
        ))

class IsTeamManager(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            User.Role.ADMIN in request.user.roles or 
            User.Role.TEAM_MANAGER in request.user.roles
        ))

class IsAdminOrManagerOrSecretaryOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        return bool(request.user and request.user.is_authenticated and (
            User.Role.ADMIN in request.user.roles or
            User.Role.USER_MANAGER in request.user.roles or
            User.Role.FIXTURE_SECRETARY in request.user.roles
        ))
