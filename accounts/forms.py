from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import User


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
    )

    password2 = forms.CharField(
        label="Password confirmation",
        widget=forms.PasswordInput,
    )

    class Meta:
        model = User
        fields = (
            "login",
            "name",
            "role",
            "is_active",
            "is_staff",
        )

    def clean_login(self) -> str:
        login = self.cleaned_data["login"].strip().lower()

        if User.objects.filter(login=login).exists():
            raise forms.ValidationError(
                "A user with this login already exists."
            )

        return login

    def clean_password2(self) -> str:
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")

        return password2

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.login = self.cleaned_data["login"]
        user.set_password(self.cleaned_data["password1"])

        if commit:
            user.save()

        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label="Password",
        help_text=(
            "Passwords are not stored in plain text, so the current password "
            "cannot be displayed."
        ),
    )

    class Meta:
        model = User
        fields = (
            "login",
            "name",
            "password",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
        )

    def clean_password(self) -> str:
        return self.initial["password"]


class LoginForm(forms.Form):
    login = forms.CharField(
        label="Login",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter login",
                "autocomplete": "username",
            }
        ),
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Enter password",
                "autocomplete": "current-password",
            }
        ),
    )