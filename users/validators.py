import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexPasswordValidator:
    def validate(self, password, user=None):
        if not re.findall(r"[A-Z]", password):
            raise ValidationError(
                _("The password must contain at least 1 uppercase letter, A-Z."),
                code="password_no_upper",
            )
        if not re.findall(r"[a-z]", password):
            raise ValidationError(
                _("The password must contain at least 1 lowercase letter, a-z."),
                code="password_no_lower",
            )
        if not re.findall(r"\d", password):
            raise ValidationError(
                _("The password must contain at least 1 digit, 0-9."),
                code="password_no_number",
            )
        if not re.findall(r"[^A-Za-z0-9]", password):
            raise ValidationError(
                _("The password must contain at least 1 special character."),
                code="password_no_special",
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least 1 uppercase letter, 1 lowercase letter, 1 digit, and 1 special character."
        )
