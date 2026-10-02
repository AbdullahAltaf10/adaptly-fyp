"""
Outgoing email for flows Firebase's own templates cannot cover — right now,
that is only the device-verification PIN (Firebase sends verification and
password-reset mail itself; this module never duplicates those).

Sends over Gmail SMTP with an app password, the same lazy-init-with-a-clear-
error pattern as `app/auth/firebase.py`: importing this module must not
require credentials to be configured, only calling `send_email` does.
"""

import os
import smtplib
from email.message import EmailMessage


class MailerNotConfigured(RuntimeError):
    pass


def _credentials() -> tuple[str, str, str]:
    address = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    sender_name = os.getenv("GMAIL_SENDER_NAME", "Adaptly")

    missing = [n for n, v in (("GMAIL_ADDRESS", address), ("GMAIL_APP_PASSWORD", app_password)) if not v]
    if missing:
        raise MailerNotConfigured(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Generate an app password at https://myaccount.google.com/apppasswords "
            "(requires 2-Step Verification on the Gmail account) and set them in backend/.env."
        )
    return address, app_password, sender_name


def is_configured() -> bool:
    """
    Whether a code could actually be sent right now — read by
    GET /auth/2fa/enabled so the frontend never gates a signed-in learner
    behind a code that can never arrive because nobody has set up Gmail yet.
    Mirrors GEMINI_API_KEY's "blank means degrade, not error" pattern.
    """
    return bool(os.getenv("GMAIL_ADDRESS")) and bool(os.getenv("GMAIL_APP_PASSWORD"))


def send_email(to_address: str, subject: str, text_body: str) -> None:
    """Send a plain-text email. Raises MailerNotConfigured if unset, or the
    underlying smtplib error if Gmail rejects the send — both are real
    failures the caller should surface, not swallow."""
    address, app_password, sender_name = _credentials()

    message = EmailMessage()
    message["From"] = f"{sender_name} <{address}>"
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(text_body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(address, app_password)
        smtp.send_message(message)
