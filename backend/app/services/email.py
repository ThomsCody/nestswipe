import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.config import settings

logger = logging.getLogger(__name__)


async def send_mention_email(
    to_email: str,
    to_name: str,
    commenter_name: str,
    comment_body: str,
    listing_title: str,
    favorite_id: int,
) -> None:
    """Send an email notification when a user is @mentioned in a comment.

    No-op if SendGrid is not configured (dev environments).
    """
    if not settings.sendgrid_api_key or not settings.sendgrid_from_email:
        logger.debug("SendGrid not configured, skipping email notification")
        return

    link = f"{settings.frontend_url}/favorites/{favorite_id}"
    html_content = f"""
    <p>Hi {to_name},</p>
    <p><strong>{commenter_name}</strong> mentioned you in a comment on <strong>{listing_title}</strong>:</p>
    <blockquote style="border-left: 3px solid #ccc; padding-left: 12px; color: #555;">
        {comment_body}
    </blockquote>
    <p><a href="{link}">View listing</a></p>
    """

    message = Mail(
        from_email=settings.sendgrid_from_email,
        to_emails=to_email,
        subject=f"{commenter_name} mentioned you on {listing_title}",
        html_content=html_content,
    )

    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        sg.send(message)
    except Exception:
        logger.exception("Failed to send mention email to %s", to_email)


async def send_assignment_email(
    to_email: str,
    to_name: str,
    assigner_name: str,
    listing_title: str,
    favorite_id: int,
) -> None:
    """Send an email notification when a user is assigned to a favorite."""
    if not settings.sendgrid_api_key or not settings.sendgrid_from_email:
        logger.debug("SendGrid not configured, skipping email notification")
        return

    link = f"{settings.frontend_url}/favorites/{favorite_id}"
    html_content = f"""
    <p>Hi {to_name},</p>
    <p><strong>{assigner_name}</strong> t'a assign\u00e9 le bien <strong>{listing_title}</strong>.</p>
    <p><a href="{link}">Voir le bien</a></p>
    """

    message = Mail(
        from_email=settings.sendgrid_from_email,
        to_emails=to_email,
        subject=f"{assigner_name} t'a assign\u00e9 {listing_title}",
        html_content=html_content,
    )

    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        sg.send(message)
    except Exception:
        logger.exception("Failed to send assignment email to %s", to_email)
