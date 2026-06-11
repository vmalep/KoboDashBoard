from django.db import models


class KoboConfig(models.Model):
    server_url = models.URLField(default='https://kobo.ifrc.org')
    api_token = models.CharField(max_length=255, blank=True)
    selected_form_uid = models.CharField(max_length=100, blank=True)
    selected_form_name = models.CharField(max_length=255, blank=True)
    cache_ttl_seconds = models.PositiveIntegerField(
        default=300,
        help_text='How long to cache API responses (seconds). 300 = 5 minutes.',
    )

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
