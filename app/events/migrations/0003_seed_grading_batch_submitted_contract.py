from django.db import migrations


CONTRACT = {
    "event_type": "grading.batch_submitted",
    "event_version": 1,
    "description": "A teacher submitted one CBE-bound grading batch.",
    "source_module": "grading",
    "allowed_producers": ["grading"],
    "allowed_consumers": ["audit"],
    "requires_tenant": True,
    "payload_schema": {
        "required": [
            "tenant_id",
            "assessment_id",
            "batch_id",
            "cohort_id",
            "learning_area_id",
            "curriculum_version_id",
            "record_count",
            "submitted_at",
        ]
    },
    "priority": "normal",
}


def seed_contract(apps, schema_editor):
    registry = apps.get_model("events", "EventTypeRegistry")
    registry.objects.get_or_create(
        event_type=CONTRACT["event_type"],
        event_version=CONTRACT["event_version"],
        defaults=CONTRACT,
    )


def unseed_contract(apps, schema_editor):
    registry = apps.get_model("events", "EventTypeRegistry")
    registry.objects.filter(
        event_type=CONTRACT["event_type"],
        event_version=CONTRACT["event_version"],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0002_seed_initial_event_contracts"),
    ]

    operations = [
        migrations.RunPython(seed_contract, reverse_code=unseed_contract),
    ]
