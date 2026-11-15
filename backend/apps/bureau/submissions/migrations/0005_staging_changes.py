"""Store only the cleansed fields that differ from the raw row (P2.1).

Existing rows keep exactly the same cleansed values: ``changes`` is computed
from ``raw`` and ``cleansed`` before ``cleansed`` is dropped.
"""

from django.db import migrations, models

FILL = """
UPDATE bureau_submissions_stagingrecord s
SET changes = COALESCE(
    (SELECT jsonb_object_agg(c.key, c.value)
       FROM jsonb_each(s.cleansed) c
      WHERE s.raw -> c.key IS DISTINCT FROM c.value),
    '{}'::jsonb
)
"""
UNFILL = "UPDATE bureau_submissions_stagingrecord SET cleansed = raw || changes"


class Migration(migrations.Migration):
    dependencies = [
        ("bureau_submissions", "0004_template_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="stagingrecord",
            name="changes",
            field=models.JSONField(
                default=dict, help_text="Fields whose cleansed value differs"
            ),
        ),
        migrations.RunSQL(FILL, UNFILL),
        migrations.RemoveField(model_name="stagingrecord", name="cleansed"),
    ]
