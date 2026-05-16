from django.db import migrations


CONTRACT = {
    "event_type": "grading.compilation_completed",
    "event_version": 1,
    "description": "A deterministic grading compilation run completed.",
    "source_module": "grading",
    "allowed_producers": ["grading"],
    "allowed_consumers": ["audit"],
    "requires_tenant": True,
    "payload_schema": {
        "required": [
            "tenant_id",
            "assessment_id",
            "compilation_run_id",
            "cohort_id",
            "learning_area_id",
            "curriculum_version_id",
            "status",
            "compiled_at",
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
        ("events", "0003_seed_grading_batch_submitted_contract"),
    ]

    operations = [
        migrations.RunPython(seed_contract, reverse_code=unseed_contract),
    ]
