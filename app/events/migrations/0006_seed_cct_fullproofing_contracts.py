from django.db import migrations


CONTRACTS = [
    {
        "event_type": "curriculum.evidence_submitted",
        "event_version": 1,
        "description": "A tenant submitted quarantined curriculum evidence.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {
            "required": [
                "tenant_id",
                "evidence_submission_id",
                "status",
                "created_at",
            ]
        },
        "priority": "normal",
    },
    {
        "event_type": "curriculum.verification_report_created",
        "event_version": 1,
        "description": "A curriculum evidence verification report was created.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {
            "required": [
                "tenant_id",
                "evidence_submission_id",
                "verification_report_id",
                "confidence_level",
                "status",
                "created_at",
            ]
        },
        "priority": "normal",
    },
    {
        "event_type": "curriculum.governance_decision_recorded",
        "event_version": 1,
        "description": "A governance decision was recorded for evidence.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {
            "required": [
                "tenant_id",
                "verification_report_id",
                "governance_decision_id",
                "status",
                "created_at",
            ]
        },
        "priority": "high",
    },
    {
        "event_type": "curriculum.rollback_candidate_created",
        "event_version": 1,
        "description": "A rollback or withdrawal candidate was recorded.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {
            "required": [
                "tenant_id",
                "rollback_candidate_id",
                "evidence_submission_id",
                "status",
                "created_at",
            ]
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
        ("events", "0005_seed_cct_fortification_contracts"),
    ]

    operations = [
        migrations.RunPython(seed_contracts, reverse_code=unseed_contracts),
    ]
