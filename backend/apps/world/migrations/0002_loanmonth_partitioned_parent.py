"""Create the partitioned parent table for LoanMonth (one partition per world)."""

from django.db import migrations

from apps.world.models import LOAN_MONTH_PARENT_SQL


class Migration(migrations.Migration):
    dependencies = [("world", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=LOAN_MONTH_PARENT_SQL,
            reverse_sql="DROP TABLE IF EXISTS world_loanmonth CASCADE;",
        ),
    ]
