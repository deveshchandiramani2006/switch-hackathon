"""
EmailService - SMTP email sender with SendGrid fallback.

Required env vars (optional - if not set, emails are logged but not sent):
  EMAIL_HOST     - SMTP host (e.g. smtp.gmail.com)
  EMAIL_PORT     - SMTP port (default 587)
  EMAIL_USER     - SMTP username
  EMAIL_PASS     - SMTP password
  EMAIL_FROM     - From address (default: noreply@nexus.ai)
  SENDGRID_API_KEY - Alternative: use SendGrid instead of raw SMTP
"""
import os
import logging

logger = logging.getLogger(__name__)

EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@nexus.ai")
SENDGRID_KEY = os.getenv("SENDGRID_API_KEY", "")


class EmailService:

    @classmethod
    def send(cls, to: str, subject: str, body: str) -> bool:
        """
        Send an email. Returns True on success, False on failure.
        If no email config is set, logs and returns False gracefully.
        """
        if not to or "@" not in to:
            logger.debug(f"EmailService: invalid/missing recipient '{to}' - skipping")
            return False

        if SENDGRID_KEY:
            return cls._send_sendgrid(to, subject, body)
        if EMAIL_HOST and EMAIL_USER:
            return cls._send_smtp(to, subject, body)

        logger.info(f"EmailService (no transport configured): TO={to} SUBJECT={subject}\n{body[:200]}")
        return False

    @classmethod
    def _send_smtp(cls, to: str, subject: str, body: str) -> bool:
        import smtplib
        from email.mime.text import MIMEText
        try:
            msg = MIMEText(body, "plain")
            msg["Subject"] = subject
            msg["From"]    = EMAIL_FROM
            msg["To"]      = to
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.sendmail(EMAIL_FROM, [to], msg.as_string())
            logger.info(f"Email sent via SMTP to {to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            return False

    @classmethod
    def _send_sendgrid(cls, to: str, subject: str, body: str) -> bool:
        try:
            import requests
            resp = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {SENDGRID_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": EMAIL_FROM},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                },
                timeout=15,
            )
            if resp.status_code in (200, 202):
                logger.info(f"Email sent via SendGrid to {to}: {subject}")
                return True
            logger.error(f"SendGrid send failed: {resp.status_code} {resp.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"SendGrid send failed: {e}")
            return False
