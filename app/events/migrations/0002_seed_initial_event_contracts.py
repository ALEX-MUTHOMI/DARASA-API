from django.db import migrations


INITIAL_CONTRACTS = [
    {
        "event_type": "tenant.school_provisioned",
        "event_version": 1,
        "description": "A school tenant was provisioned.",
        "source_module": "tenant",
        "allowed_producers": ["tenant"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["school_id"]},
        "priority": "high",
    },
    {
        "event_type": "core.role_assigned",
        "event_version": 1,
        "description": "A tenant-scoped role binding was assigned.",
        "source_module": "core",
        "allowed_producers": ["core", "tenant"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["user_id", "role_code"]},
        "priority": "normal",
    },
    {
        "event_type": "academics.academic_year_activated",
        "event_version": 1,
        "description": "A tenant academic year became active.",
        "source_module": "academics",
        "allowed_producers": ["academics"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["academic_year_id"]},
        "priority": "normal",
    },
    {
        "event_type": "curriculum.version_published",
        "event_version": 1,
        "description": "A curriculum version was published after review.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {"required": ["curriculum_version_id"]},
        "priority": "high",
    },
    {
        "event_type": "curriculum.diff_created",
        "event_version": 1,
        "description": "A curriculum diff was created for review.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {"required": ["curriculum_diff_id"]},
        "priority": "normal",
    },
    {
        "event_type": "regulatory.notice_verified",
        "event_version": 1,
        "description": "A regulatory notice was verified from official evidence.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {"required": ["regulatory_notice_id"]},
        "priority": "high",
    },
    {
        "event_type": "teacher.readiness_requirement_created",
        "event_version": 1,
        "description": "A teacher readiness requirement was recorded.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": False,
        "payload_schema": {"required": ["teacher_readiness_requirement_id"]},
        "priority": "normal",
    },
    {
        "event_type": "principal.notification_issued",
        "event_version": 1,
        "description": "A principal evidence card was issued to a school.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["notification_id"]},
        "priority": "high",
    },
    {
        "event_type": "school.update_acknowledged",
        "event_version": 1,
        "description": "A school acknowledged an update evidence card.",
        "source_module": "curriculum",
        "allowed_producers": ["curriculum"],
        "allowed_consumers": ["audit"],
        "requires_tenant": True,
        "payload_schema": {"required": ["acknowledgement_id"]},
        "priority": "normal",
    },
]


def seed_contracts(apps, schema_editor):
    registry = apps.get_model("events", "EventTypeRegistry")
    for contract in INITIAL_CONTRACTS:
        registry.objects.get_or_create(
            event_type=contract["event_type"],
            event_version=contract["event_version"],
            defaults=contract,
        )


def unseed_contracts(apps, schema_editor):
    registry = apps.get_model("events", "EventTypeRegistry")
    keys = [
        (contract["event_type"], contract["event_version"])
        for contract in INITIAL_CONTRACTS
    ]
    for event_type, event_version in keys:
        registry.objects.filter(
            event_type=event_type,
            event_version=event_version,
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0001_initial_event_backbone"),
    ]

    operations = [
        migrations.RunPython(seed_contracts, reverse_code=unseed_contracts),
    ]
