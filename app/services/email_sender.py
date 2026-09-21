"""
Third-party email delivery, abstracted behind :class:`EmailSender`.

``UserService`` never talks to an email provider directly -- it calls
``EmailSender.send(reason, to, context)`` and lets the sender pick the right
template for ``reason``. ``NoopEmailSender`` below is the only
implementation right now: it resolves the template and logs what it would
have sent, but delivers nothing. Swap it for a real provider (SES,
SendGrid, SMTP, ...) by implementing :class:`EmailSender` and changing what
``get_email_sender`` (in ``app.api.dependencies.users``) constructs -- no
change needed in ``UserService`` itself.
"""

import enum
from collections.abc import Mapping
from typing import Any, Protocol

from app.log import logger


class EmailReason(enum.StrEnum):
    """Why an email is being sent -- selects which template to use."""

    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"  # noqa: S105
    OTP = "otp"


class EmailSender(Protocol):
    """Third-party email delivery, chosen by :class:`EmailReason`."""

    async def send(
        self, reason: EmailReason, to: str, context: Mapping[str, Any]
    ) -> None:
        """
        Send the template for ``reason`` to ``to``.

        :param reason: why this email is being sent; selects the template.
        :param to: recipient address.
        :param context: template variables (e.g. a token or an OTP code).
        """
        ...


# Maps each reason to the template that should render it. Swap these for
# your real template names/ids once you wire up a provider.
TEMPLATES: dict[EmailReason, str] = {
    EmailReason.VERIFY_EMAIL: "verify_email",
    EmailReason.RESET_PASSWORD: "reset_password",
    EmailReason.OTP: "otp",
}


class NoopEmailSender:
    """
    Template-aware email sender that doesn't actually send anything.

    TODO: replace the body of :meth:`send` with a real call to your email
    provider once you're ready -- the template lookup by reason is already
    done for you.
    """

    async def send(
        self, reason: EmailReason, to: str, context: Mapping[str, Any]
    ) -> None:
        """
        Log the template that would have been sent.

        :param reason: why this email is being sent; selects the template.
        :param to: recipient address.
        :param context: template variables (e.g. a token or an OTP code).
        """
        template = TEMPLATES[reason]
        logger.info(
            "Would send template {} to {} with context {}", template, to, dict(context)
        )
