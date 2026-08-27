from django.http import JsonResponse
from django.utils import timezone


class PasswordExpiryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Skip password change endpoints
            if request.path.startswith("/api/users/change-password"):
                return self.get_response(request)

            # Check if password needs to be reset
            if request.user.force_password_reset:
                return self._forbidden_response("FORCE_RESET")

            # Check if password is older than 365 days
            if request.user.last_password_change:
                days_since_change = (
                    timezone.now() - request.user.last_password_change
                ).days
                if days_since_change >= 365:
                    return self._forbidden_response("PASSWORD_EXPIRED")

        return self.get_response(request)

    def _forbidden_response(self, code):
        return JsonResponse(
            {"detail": "Password reset required.", "code": code}, status=403
        )
