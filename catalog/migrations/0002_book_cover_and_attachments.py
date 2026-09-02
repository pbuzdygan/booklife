from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="book",
            name="cover_filename",
            field=models.CharField(blank=True, editable=False, max_length=80),
        ),
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("original_name", models.CharField(max_length=160)),
                ("stored_filename", models.CharField(editable=False, max_length=80, unique=True)),
                ("content_type", models.CharField(editable=False, max_length=80)),
                ("size", models.PositiveIntegerField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "book",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="catalog.book",
                    ),
                ),
            ],
            options={"ordering": ("created_at",)},
        ),
    ]
