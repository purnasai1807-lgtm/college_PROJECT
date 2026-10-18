"""Minimal SMTP email sender. Failures are logged and never raised to the caller."""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from app.config import get_settings

logger = logging.getLogger("ace_canteen.email")

def send_email(to_address: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not settings.smtp_host:
        if settings.environment.lower() in {"production", "prod"}:
            logger.warning("SMTP is not configured; email '%s' was not sent. Set SMTP_HOST and related settings.", subject)
        else:
            # Development convenience only: lets you click the link from the console.
            logger.info("DEV EMAIL (SMTP not configured) to=%s subject=%s\n%s", to_address, subject, body)
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    try:
        context = ssl.create_default_context()
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=context) as smtp:
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.starttls(context=context)
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send email '%s'", subject)
        return False
