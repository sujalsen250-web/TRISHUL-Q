"""Centralized email service for TRISHUL-Q (SMTP).

Every application email goes through this module so configuration, error
handling and logging stay in one place.  Credentials come from the environment
(see .env.example) and are NEVER logged or returned in API responses.

Supported emails:
  * admin welcome / credentials  (to the Super Admin for review + forwarding)
  * password reset link
  * password changed confirmation
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from . import config

log = logging.getLogger("trishulq.mail")

_SECRET_HINTS = ("password", "secret", "token", "credential")


def is_configured() -> bool:
    return config.smtp_configured()


def _safe(text: str) -> str:
    """Strip anything that looks like a secret before logging."""
    low = (text or "").lower()
    if any(h in low for h in _SECRET_HINTS):
        return "[redacted]"
    return text


def _connect():
    if config.SMTP_USE_SSL:
        ctx = ssl.create_default_context()
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT,
                                  timeout=15, context=ctx)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
        server.ehlo()
        if config.SMTP_USE_TLS:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
    if config.SMTP_USERNAME:
        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
    return server


def check_mail() -> dict:
    """Verify the SMTP configuration by opening (and closing) a connection."""
    if not is_configured():
        return {"configured": False, "ok": False,
                "message": "SMTP is not configured (set SMTP_HOST in .env)"}
    try:
        server = _connect()
        server.quit()
        log.info("SMTP check OK for host=%s", config.SMTP_HOST)
        return {"configured": True, "ok": True, "host": config.SMTP_HOST,
                "port": config.SMTP_PORT, "from": config.SMTP_FROM_EMAIL,
                "message": "SMTP connection OK"}
    except Exception as exc:
        log.warning("SMTP check failed: %s", type(exc).__name__)
        return {"configured": True, "ok": False, "host": config.SMTP_HOST,
                "port": config.SMTP_PORT,
                "message": f"SMTP check failed: {type(exc).__name__}: {_safe(str(exc))}"}


def send_mail(to: str, subject: str, body: str) -> dict:
    """Send a plain-text email. Returns {sent, message}. Never raises."""
    if not to:
        return {"sent": False, "message": "No recipient"}
    if not is_configured():
        log.warning("Email skipped (SMTP not configured): %s", subject)
        return {"sent": False,
                "message": "SMTP not configured -- message not sent"}
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = (f"{config.SMTP_FROM_NAME} <{config.SMTP_FROM_EMAIL}>"
                   if config.SMTP_FROM_NAME else config.SMTP_FROM_EMAIL)
    msg["To"] = to
    msg.set_content(body)
    try:
        server = _connect()
        server.send_message(msg)
        server.quit()
        log.info("Email sent: to=%s subject=%s", to, subject)
        return {"sent": True, "message": f"Sent to {to}"}
    except Exception as exc:
        log.warning("Email send failed to=%s: %s", to, type(exc).__name__)
        return {"sent": False,
                "message": f"Send failed: {type(exc).__name__}: {_safe(str(exc))}"}


# --------------------------------------------------------------- templates ---
def login_url() -> str:
    return f"{config.PUBLIC_BASE_URL.rstrip('/')}/login"


def admin_welcome_message(full_name: str, email: str, password: str,
                          role: str = "Administrator") -> str:
    """Plain-text welcome message (also used by the 'Copy Welcome Message' button)."""
    return (
        f"Congratulations {full_name}!\n\n"
        f"Your {config.APP_NAME} Admin account has been successfully created.\n\n"
        f"Name: {full_name}\n"
        f"Email: {email}\n"
        f"Temporary Password: {password}\n"
        f"Role: {role}\n\n"
        f"Login:\n{login_url()}\n\n"
        f"Please change your temporary password after your first login.\n\n"
        f"Welcome to {config.APP_NAME} Security Administration.\n"
    )


def admin_welcome_email(full_name: str, email: str, password: str,
                        role: str = "Administrator") -> tuple[str, str]:
    subject = f"Congratulations — Your {config.APP_NAME} Admin Account Has Been Created"
    return subject, admin_welcome_message(full_name, email, password, role)


def password_reset_email(full_name: str, reset_link: str,
                         ttl_minutes: int) -> tuple[str, str]:
    subject = f"{config.APP_NAME} — Password Reset"
    body = (
        f"Hello {full_name or 'there'},\n\n"
        f"We received a request to reset your {config.APP_NAME} password.\n\n"
        f"Reset your password using this link (valid for {ttl_minutes} minutes, "
        f"single use):\n\n{reset_link}\n\n"
        f"If you did not request this, you can safely ignore this email — your "
        f"password will not change.\n\n"
        f"-- {config.APP_NAME}\n"
    )
    return subject, body


def password_changed_email(full_name: str) -> tuple[str, str]:
    subject = f"{config.APP_NAME} — Your password was changed"
    body = (
        f"Hello {full_name or 'there'},\n\n"
        f"Your {config.APP_NAME} password was changed successfully.\n\n"
        f"If this was not you, contact your administrator immediately.\n\n"
        f"-- {config.APP_NAME}\n"
    )
    return subject, body
