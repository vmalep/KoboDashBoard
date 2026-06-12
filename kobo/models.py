from django.db import models


class KoboConfig(models.Model):
    server_url = models.URLField(default='https://kobo.ifrc.org')
    api_token = models.CharField(max_length=255, blank=True)

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


class ConfiguredForm(models.Model):
    uid = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    cache_ttl_seconds = models.PositiveIntegerField(default=300)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name or self.uid
