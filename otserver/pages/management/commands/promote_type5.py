from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from pages.ot_models import Accounts as Account

class Command(BaseCommand):
    help = "Sync all Account(type=5) to Django superusers"

    def handle(self, *args, **opts):
        User = get_user_model()
        promoted = 0
        for acc in Account.objects.filter(type=6):
            username = getattr(acc, "id", None) or getattr(acc, "id", None)
            if not username:
                self.stdout.write(self.style.WARNING(f"Skip account id={acc.pk}: no username"))
                continue
            email = getattr(acc, "email", "") or ""
            user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
            user.is_staff = True
            user.is_superuser = True
            #if not user.has_usable_password():
            #    # You can skip this if you use external auth
            #    user.set_password(User.objects.make_random_password())
            user.save()
            promoted += 1
        self.stdout.write(self.style.SUCCESS(f"Promoted/synced {promoted} user(s)."))
