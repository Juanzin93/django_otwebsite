from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

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
    


class CreateCharacterForm(forms.Form):
    name = forms.CharField(max_length=30)
    if settings.WAR_SERVER_ENABLED:
        vocation = forms.TypedChoiceField(choices=[(v, name) for v, name in VOCATION_CHOICES if v != 0], coerce=int)
    else:
        vocation = forms.TypedChoiceField(choices=[(0, "None")], coerce=int)
    sex = forms.TypedChoiceField(choices=SEX_CHOICES, coerce=int)
    town_id = forms.IntegerField(min_value=1, required=False)

    def clean_name(self):
        n = self.cleaned_data["name"].strip()
        if len(n) < 3:
            raise ValidationError("Name must be at least 3 characters.")
        import re
        if not re.fullmatch(r"[A-Za-z ]+", n):
            raise ValidationError("Name may contain only letters and spaces.")
        return n