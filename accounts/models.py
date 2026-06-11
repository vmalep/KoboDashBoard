from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

COUNTRY_CHOICES = [
    ('BFA', 'Burkina Faso'),
    ('BDI', 'Burundi'),
    ('MAL', 'Mali'),
    ('NIG', 'Niger'),
    ('RDC', 'RDC'),
    ('HQ',  'Siège / HQ'),
]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=200)
    country = models.CharField(max_length=3, choices=COUNTRY_CHOICES)

    def __str__(self):
        return f'{self.full_name} ({self.country})'
