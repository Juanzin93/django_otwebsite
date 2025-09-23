from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

class News(models.Model):
    title        = models.CharField(max_length=200)
    slug         = models.SlugField(max_length=220, unique=True, blank=True)
    summary      = models.TextField(blank=True)
    body         = models.TextField()
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['-published_at']),
            models.Index(fields=['is_published']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200] or "post"
            slug = base
            i = 2
            while News.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

User = get_user_model()

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    ot_account_id = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"Profile({self.user})"

# Map to your OT server tables (read-only)
class Player(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=255)
    level = models.IntegerField()
    vocation = models.IntegerField()
    account_id = models.IntegerField()

    class Meta:
        managed = False
        db_table = "players"
