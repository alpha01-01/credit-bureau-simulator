"""Record the data standard each submission and run used (D19).

Everything already stored was made under data standard 1.1, so existing rows
are filled with "1.1".
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bureau_submissions", "0003_alter_submissionfile_file_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="template_version",
            field=models.CharField(
                default="1.1",
                help_text="Data standard in force for the reporting period (D19)",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="processingrun",
            name="template_version",
            field=models.CharField(
                default="1.1",
                help_text="Data standard the records were judged under (D19)",
                max_length=20,
            ),
            preserve_default=False,
        ),
    ]
