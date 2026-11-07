"""
EmailService - SMTP email sender.

Required env vars (optional - if not set, emails are logged but not sent):
  SMTP_HOST     - SMTP host (e.g. sandbox.smtp.mailtrap.io)
  SMTP_PORT     - SMTP port (default 587)
  SMTP_USER     - SMTP username
  SMTP_PASSWORD - SMTP password
  EMAIL_FROM    - From address (default: nexus@nexus.ai)
  SENDGRID_API_KEY - Alternative: use SendGrid instead of raw SMTP
"""
import os
import logging

logger = logging.getLogger(__name__)

SMTP_HOST    = os.getenv("SMTP_HOST", "")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER    = os.getenv("SMTP_USER", "")
SMTP_PASS    = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM   = os.getenv("EMAIL_FROM", "nexus@nexus.ai")
SENDGRID_KEY = os.getenv("SENDGRID_API_KEY", "")


class EmailService:

    @classmethod
    def send(cls, to: str, subject: str, body: str) -> bool:
        if not to or "@" not in to:
            logger.debug(f"EmailService: invalid/missing recipient '{to}' - skipping")
            return False

        if SENDGRID_KEY:
            return cls._send_sendgrid(to, subject, body)
        if SMTP_HOST and SMTP_USER:
            return cls._send_smtp(to, subject, body)

        logger.info(f"EmailService (no transport configured): TO={to} SUBJECT={subject}\n{body[:200]}")
        return False

    @classmethod
    def send_escalation(cls, to: str, level: int, lead_name: str, deal_value: str,
                        days_overdue: int, commitment_text: str, llm_message: str) -> bool:
        level_labels = {1: "Rep", 2: "Team Lead", 3: "Manager", 4: "VP", 5: "CEO"}
        label = level_labels.get(level, f"Level {level}")

        subject = f"[NEXUS Escalation — Level {level} / {label}] {lead_name} · {days_overdue}d overdue"

        body = f"""NEXUS Escalation Engine — Level {level} ({label})
{'=' * 60}

Lead:        {lead_name}
Deal Value:  {deal_value}
Days Overdue: {days_overdue}
Commitment:  {commitment_text}

{'─' * 60}
MESSAGE SENT TO {label.upper()}:
{'─' * 60}

{llm_message}

{'─' * 60}
Escalation will continue to the next level unless the
commitment is marked resolved in NEXUS.

— NEXUS Escalation Engine
"""
        return cls.send(to=to, subject=subject, body=body)

    @classmethod
    def _send_smtp(cls, to: str, subject: str, body: str) -> bool:
        import smtplib
        from email.mime.text import MIMEText
        try:
            msg = MIMEText(body, "plain")
            msg["Subject"] = subject
            msg["From"]    = EMAIL_FROM
            msg["To"]      = to
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
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
