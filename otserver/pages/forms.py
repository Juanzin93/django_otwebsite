from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .db import DB

db = DB(retries=2)

User = get_user_model()

VOCATION_CHOICES = [
    (0, "None"),
    (1, "Sorcerer"),
    (2, "Druid"),
    (3, "Paladin"),
    (4, "Knight"),
]

SEX_CHOICES = [(0, "Female"), (1, "Male")]  # TFS usually: 0=female, 1=male

class EmailUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email"]
        widgets = {
            "email": forms.EmailInput(attrs={"required": True}),
        }


class SignUpForm(forms.Form):
    username   = forms.CharField(max_length=30)
    email      = forms.EmailField()
    password1  = forms.CharField(widget=forms.PasswordInput)
    password2  = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        u = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=u).exists():
            raise forms.ValidationError("This username is taken.")
        return u

    def clean_email(self):
        e = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=e).exists():
            raise forms.ValidationError("This email is already in use.")
        return e

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned
    



def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

class CreateCharacterForm(forms.Form):
    name     = forms.CharField(max_length=30)
    world    = forms.TypedChoiceField(choices=(), coerce=int, required=True, label="World")
    vocation = forms.TypedChoiceField(choices=(), coerce=int, required=True, label="Vocation")
    sex      = forms.TypedChoiceField(choices=SEX_CHOICES, coerce=int, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1) Load worlds (use your helper’s "select" -> list of dict rows)
        rows = db.run("select", "SELECT id, name FROM worlds ORDER BY id", {}) or []
        world_choices = [(int(r["id"]), r["name"]) for r in rows] or [(1, "World 1")]
        # TypedChoiceField: provide STRING values; coerce=int converts on cleaned_data
        self.fields["world"].choices = [(str(i), n) for i, n in world_choices]

        # Maps for lookups
        id2name    = {i: n for i, n in world_choices}
        strid2name = {str(i): n for i, n in world_choices}

        # 2) Determine selected world (POST > initial > first)
        if self.is_bound:
            selected_world_raw = self.data.get(self.add_prefix("world")) or self.data.get("world")
        else:
            selected_world_raw = self.initial.get("world")

        if not selected_world_raw and world_choices:
            selected_world_raw = str(world_choices[0][0])

        selected_world_id = _int_or_none(selected_world_raw)
        selected_world_name = (
            strid2name.get(str(selected_world_raw))
            or id2name.get(selected_world_id)
            or ""
        )

        # 3) WAR detection — by ID (and optionally by name), only if enabled
        war_enabled = bool(getattr(settings, "WAR_SERVER_ENABLED", False))
        # Ensure IDs are ints
        war_ids = {int(x) for x in getattr(settings, "WAR_WORLD_IDS", [])}
        war_names = {s.strip().lower() for s in getattr(settings, "WAR_WORLD_NAMES", ["WAR"])}

        is_war_world = war_enabled and (
            (selected_world_id is not None and selected_world_id in war_ids) or
            (selected_world_name.strip().lower() in war_names)
        )

        # 4) Set vocation choices (STRING values!)
        if is_war_world:
            # e.g. [(1,"Sorcerer"), (2,"Druid"), (3,"Paladin"), (4,"Knight")]
            voc_choices = [(str(v), label) for v, label in VOCATION_CHOICES if v != 0]
        else:
            voc_choices = [("0", "None")]

        self.fields["vocation"].choices = voc_choices

    def clean_name(self):
        n = self.cleaned_data["name"].strip()
        if len(n) < 3:
            raise ValidationError("Name must be at least 3 characters.")
        import re
        if not re.fullmatch(r"[A-Za-z ]+", n):
            raise ValidationError("Name may contain only letters and spaces.")
        return n

