from django.db import migrations


CONTRACTS = [
    {
        "event_type": "curriculum.school_adoption_scheduled",
        "event_version": 1,
        "description": "A school scheduled adoption of a published curriculum.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {
            "required": [
                "tenant_id",
                "curriculum_version_id",
                "adoption_id",
                "effective_from",
            ]
        },
        "priority": "normal",
    },
    {
        "event_type": "curriculum.version_withdrawn",
        "event_version": 1,
        "description": "A curriculum version was withdrawn from new adoption.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {
            "required": [
                "curriculum_version_id",
                "withdrawal_id",
                "withdrawn_at",
            ]
        },
        "priority": "high",
    },
    {
        "event_type": "curriculum.rollback_planned",
        "event_version": 1,
        "description": "A tenant-scoped curriculum rollback plan was recorded.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {
            "required": [
                "tenant_id",
                "rollback_plan_id",
                "withdrawn_version_id",
                "affected_assessment_count",
            ]
        },
        "priority": "high",
    },
    {
        "event_type": "curriculum.notice_batch_created",
        "event_version": 1,
        "description": "A bounded curriculum notice batch was created.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {
            "required": ["notice_batch_id", "notice_type", "total_count"]
        },
        "priority": "normal",
    },
]


def seed_contracts(apps, schema_editor):
    registry = apps.get_model("events", "EventTypeRegistry")
    for contract in CONTRACTS:
        registry.objects.get_or_create(
            event_type=contract["event_type"],
            event_version=contract["event_version"],
            defaults=contract,
        )


def unseed_contracts(apps, schema_editor):
    registry = apps.get_model("events", "EventTypeRegistry")
    for contract in CONTRACTS:
        registry.objects.filter(
            event_type=contract["event_type"],
            event_version=contract["event_version"],
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0004_seed_grading_compilation_completed_contract"),
    ]

    operations = [
        migrations.RunPython(seed_contracts, reverse_code=unseed_contracts),
    ]
