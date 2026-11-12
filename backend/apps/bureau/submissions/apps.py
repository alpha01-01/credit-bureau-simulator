from django.apps import AppConfig


class BureauSubmissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bureau.submissions"
    label = "bureau_submissions"
    verbose_name = "Submissions"
