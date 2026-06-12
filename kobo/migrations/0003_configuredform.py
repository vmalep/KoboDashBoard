from django.db import migrations, models


def migrate_existing_form(apps, schema_editor):
    """Copy the previously selected form into ConfiguredForm."""
    KoboConfig = apps.get_model('kobo', 'KoboConfig')
    ConfiguredForm = apps.get_model('kobo', 'ConfiguredForm')
    try:
        config = KoboConfig.objects.get(pk=1)
        if config.selected_form_uid:
            ConfiguredForm.objects.create(
                uid=config.selected_form_uid,
                name=config.selected_form_name or config.selected_form_uid,
                cache_ttl_seconds=config.cache_ttl_seconds,
                order=0,
            )
    except KoboConfig.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('kobo', '0002_koboconfig_selected_form_name_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguredForm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uid', models.CharField(max_length=100, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('cache_ttl_seconds', models.PositiveIntegerField(default=300)),
                ('order', models.PositiveIntegerField(default=0)),
            ],
            options={'ordering': ['order', 'name']},
        ),
        migrations.RunPython(migrate_existing_form, migrations.RunPython.noop),
        migrations.RemoveField(model_name='koboconfig', name='selected_form_uid'),
        migrations.RemoveField(model_name='koboconfig', name='selected_form_name'),
        migrations.RemoveField(model_name='koboconfig', name='cache_ttl_seconds'),
    ]
