from django.apps import AppConfig


class BureauQualityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bureau.quality"
    label = "bureau_quality"
    verbose_name = "Data quality"
