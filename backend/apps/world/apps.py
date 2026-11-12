from django.apps import AppConfig


class WorldConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.world"
    label = "world"
    verbose_name = "World (ground truth)"
