from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import COUNTRY_CHOICES

User = get_user_model()


class RegistrationForm(forms.Form):
    full_name = forms.CharField(
        label='Nom complet',
        max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'Prénom Nom'}),
    )
    country = forms.ChoiceField(label='Pays / Entité', choices=[('', '— Sélectionner —')] + COUNTRY_CHOICES)
    email = forms.EmailField(label='Adresse email')
    password1 = forms.CharField(label='Mot de passe', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmer le mot de passe', widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Cette adresse email est déjà enregistrée.')
        return email

    def clean_country(self):
        country = self.cleaned_data.get('country')
        if not country:
            raise forms.ValidationError('Veuillez sélectionner un pays ou une entité.')
        return country

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2:
            if p1 != p2:
                self.add_error('password2', 'Les mots de passe ne correspondent pas.')
            else:
                try:
                    validate_password(p1)
                except forms.ValidationError as e:
                    self.add_error('password1', e)
        return cleaned

    def save(self):
        from .models import UserProfile
        email = self.cleaned_data['email']
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data['password1'],
            is_active=False,
        )
        UserProfile.objects.create(
            user=user,
            full_name=self.cleaned_data['full_name'],
            country=self.cleaned_data['country'],
        )
        return user
