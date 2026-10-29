from datetime import datetime, timezone
from email.message import EmailMessage
import smtplib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.user import User
from .models import CompetitionNotification, PlatformEntry


def _message(entry, email):
    message = EmailMessage()
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = email
    message["Subject"] = f"مسابقة جديدة على WE MATH: {entry.title}"
    message.set_content(
        f"تم نشر مسابقة جديدة على منصة WE MATH.\n\n{entry.title}\n{entry.summary}\n"
        f"التاريخ: {entry.event_date or 'يحدد لاحقًا'}\n\nسجّل الدخول إلى المنصة للاطلاع على التفاصيل."
    )
    return message


def dispatch_competition_email(entry_id: str):
    db = SessionLocal()
    try:
        entry = db.get(PlatformEntry, entry_id)
        if not entry or entry.section != "competitions" or not entry.published:
            return
        users = db.scalars(select(User).where(User.email.is_not(None)).order_by(User.id)).all()
        if not settings.SMTP_HOST:
            return
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
            for user in users:
                existing = db.scalar(select(CompetitionNotification).where(CompetitionNotification.entry_id == entry_id, CompetitionNotification.user_id == user.id))
                if existing and existing.status == "sent":
                    continue
                row = existing or CompetitionNotification(entry_id=entry_id, user_id=user.id, email=user.email, status="pending")
                if not existing:
                    db.add(row)
                    try:
                        db.flush()
                    except IntegrityError:
                        db.rollback()
                        continue
                try:
                    smtp.send_message(_message(entry, user.email))
                    row.status, row.error = "sent", None
                except Exception as exc:  # retain a retryable audit record; do not fail other recipients.
                    row.status, row.error = "failed", str(exc)[:500]
                row.attempted_at = datetime.now(timezone.utc)
                db.commit()
    finally:
        db.close()
