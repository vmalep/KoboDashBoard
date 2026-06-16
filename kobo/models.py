from django.conf import settings
from django.db import models


class KoboConfig(models.Model):
    server_url = models.URLField(default='https://kobo.ifrc.org')
    api_token = models.CharField(max_length=255, blank=True)
    org_name = models.CharField(max_length=200, blank=True, default='')
    logo = models.FileField(upload_to='branding/', blank=True, null=True)
    brand_color = models.CharField(max_length=7, blank=True, default='')

    class Meta:
        verbose_name = 'KoboToolBox Configuration'
        verbose_name_plural = 'KoboToolBox Configuration'

    def __str__(self):
        return self.server_url

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Singleton: prevent deletion

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class DashboardGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='dashboard_groups', blank=True)
    admins = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='administered_groups', blank=True)
    forms = models.ManyToManyField(
        'ConfiguredForm', related_name='groups', blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ConfiguredForm(models.Model):
    uid = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    cache_ttl_seconds = models.PositiveIntegerField(default=300)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name or self.uid


class DashboardConfig(models.Model):
    form = models.ForeignKey(
        ConfiguredForm, on_delete=models.CASCADE, related_name='dashboard_configs')
    name = models.CharField(max_length=200)
    schema_version = models.PositiveIntegerField(default=1)
    config = models.JSONField(default=dict)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} — {self.form}'
