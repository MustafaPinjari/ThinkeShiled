from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings


@shared_task(bind=True, max_retries=3)
def send_lockout_email_task(self, user_id):
    """Send account lockout notification email to the user."""
    from authentication.models import User

    try:
        user = User.objects.get(pk=user_id)
        send_mail(
            subject="TenderShield: Account Locked",
            message=(
                f"Hello {user.username},\n\n"
                "Your account has been temporarily locked due to 5 consecutive failed login attempts.\n"
                f"It will be unlocked at: {user.locked_until.isoformat() if user.locked_until else 'N/A'}\n\n"
                "If this was not you, please contact your administrator immediately.\n\n"
                "TenderShield Security Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except User.DoesNotExist:
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
