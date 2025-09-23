from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Profile
from .ot_models import Accounts as Account
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

User = get_user_model()


@receiver(post_save, sender=Account)
def sync_admin_flags(sender, instance, **kwargs):
    User = get_user_model()
    username = getattr(instance, "name", None) or getattr(instance, "username", None)
    if not username:
        return
    user, _ = User.objects.get_or_create(username=username, defaults={"email": getattr(instance, "email", "")})
    is_admin = (instance.type == 6)
    if user.is_staff != is_admin or user.is_superuser != is_admin:
        user.is_staff = is_admin
        user.is_superuser = is_admin
        user.save()

@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)

#@receiver(post_save, sender=User)
def send_welcome_email(sender, instance: User, created: bool, **kwargs):
    # Only on first creation and only if the user has an email
    if not created or not instance.email:
        return

    ctx = {
        "username": instance.username,
        "site_name": "Retrowar OT",
    }

    subject = "Welcome to Retrowar OT!"
    text_body = render_to_string("emails/signup_confirm.txt", ctx)
    html_body = render_to_string("emails/signup_confirm.html", ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[instance.email],
        reply_to=[getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL)],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)