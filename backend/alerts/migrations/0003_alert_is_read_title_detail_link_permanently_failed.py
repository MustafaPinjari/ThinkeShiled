from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="title",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="alert",
            name="detail_link",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="alert",
            name="is_read",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="alert",
            name="delivery_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("DELIVERED", "Delivered"),
                    ("FAILED", "Failed"),
                    ("RETRYING", "Retrying"),
                    ("PERMANENTLY_FAILED", "Permanently Failed"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
    ]
