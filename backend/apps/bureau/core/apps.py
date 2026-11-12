from django.apps import AppConfig


class BureauCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bureau.core"
    label = "bureau_core"
    verbose_name = "Bureau core"
