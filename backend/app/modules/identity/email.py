from email.message import EmailMessage
from typing import Protocol

import aiosmtplib
import structlog

from app.core.config import Settings

_log = structlog.get_logger("email")


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def send(self, *, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._s.email_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        await aiosmtplib.send(
            msg,
            hostname=self._s.smtp_host,
            port=self._s.smtp_port,
            username=self._s.smtp_username,
            password=self._s.smtp_password.get_secret_value() if self._s.smtp_password else None,
            start_tls=self._s.smtp_starttls,
            timeout=10,
        )


async def safe_send(sender: EmailSender, *, to: str, subject: str, body: str) -> None:
    """Delivery failures must not change the HTTP response (that would reveal account existence)."""
    try:
        await sender.send(to=to, subject=subject, body=body)
    except Exception:
        _log.error("email_send_failed", exc_info=True)


def reset_email(locale: str, link: str, ttl_minutes: int) -> tuple[str, str]:
    if locale == "ar":
        return (
            "إعادة تعيين كلمة المرور",
            "تلقّينا طلباً لإعادة تعيين كلمة مرور حسابك.\n\n"
            f"افتح هذا الرابط لاختيار كلمة مرور جديدة "
            f"(صالح لمدة {ttl_minutes} دقيقة، ويُستخدم مرة واحدة):\n"
            f"{link}\n\n"
            "إذا لم تطلب ذلك فتجاهل هذه الرسالة؛ لن يتغيّر شيء.\n",
        )
    return (
        "Reset your password",
        "We received a request to reset your account password.\n\n"
        f"Open this link to choose a new password (valid for {ttl_minutes} minutes, single use):\n"
        f"{link}\n\n"
        "If you didn't request this, ignore this email; nothing will change.\n",
    )


def invitation_email(
    locale: str, org_name: str, inviter: str, link: str, ttl_days: int
) -> tuple[str, str]:
    if locale == "ar":
        return (
            f"دعوة للانضمام إلى {org_name}",
            f"دعاك {inviter} للانضمام إلى مساحة العمل «{org_name}».\n\n"
            f"افتح هذا الرابط لقبول الدعوة (صالح لمدة {ttl_days} أيام، ويُستخدم مرة واحدة):\n"
            f"{link}\n\n"
            "إذا لم تكن تتوقع هذه الدعوة فتجاهل هذه الرسالة.\n",
        )
    return (
        f"You're invited to join {org_name}",
        f'{inviter} invited you to join the workspace "{org_name}".\n\n'
        f"Open this link to accept (valid for {ttl_days} days, single use):\n"
        f"{link}\n\n"
        "If you weren't expecting this invitation, ignore this email.\n",
    )
