# Migration: extend User model with agency FK, email_verified flag, and new roles.
# Satisfies Requirements 2.2, 2.3, 3.1, 9.2

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0001_initial"),
        ("agencies", "0001_initial"),
    ]

    operations = [
        # 1. Widen the role column to accommodate longer role names (GOVERNMENT_AUDITOR = 18 chars)
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("AUDITOR", "Auditor"),
                    ("ADMIN", "Administrator"),
                    ("AGENCY_ADMIN", "Agency Administrator"),
                    ("AGENCY_OFFICER", "Agency Officer"),
                    ("REVIEWER", "Reviewer"),
                    ("GOVERNMENT_AUDITOR", "Government Auditor"),
                ],
                default="AUDITOR",
                max_length=20,
            ),
        ),
        # 2. Add agency FK (nullable — internal users have no agency)
        migrations.AddField(
            model_name="user",
            name="agency",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="members",
                to="agencies.agency",
            ),
        ),
        # 3. Add email_verified flag
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
    ]
