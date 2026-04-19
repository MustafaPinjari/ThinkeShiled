# Migration: add delivery_failed field to EmailVerificationToken.
# Required by Task 3.3 (Requirement 1.8).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailverificationtoken",
            name="delivery_failed",
            field=models.BooleanField(default=False),
        ),
    ]
