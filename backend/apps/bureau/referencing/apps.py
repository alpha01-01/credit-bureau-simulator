from django.apps import AppConfig


class BureauReferencingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bureau.referencing"
    label = "bureau_referencing"
    verbose_name = "Referencing"
