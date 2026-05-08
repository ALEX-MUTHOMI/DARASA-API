from __future__ import annotations

from core.models import Role


DEFAULT_ROLE_DESCRIPTIONS = {
    Role.RoleCode.PRINCIPAL: "School-wide administrative capability.",
    Role.RoleCode.DEPUTY_PRINCIPAL: "Delegated school leadership capability.",
    Role.RoleCode.HOD: "Department-level coordination capability.",
    Role.RoleCode.CLASS_TEACHER: "Class-level pastoral and academic capability.",
    Role.RoleCode.SUBJECT_TEACHER: "Subject instruction capability.",
    Role.RoleCode.SCHOOL_ADMIN: "School operations administration capability.",
    Role.RoleCode.GUARDIAN: "Learner guardian access capability.",
    Role.RoleCode.AUDITOR: "Read-only compliance review capability.",
}


def ensure_default_roles() -> list[Role]:
    roles: list[Role] = []
    for role_code in Role.RoleCode:
        role, _ = Role.objects.get_or_create(
            code=role_code.value,
            defaults={
                "name": role_code.label,
                "description": DEFAULT_ROLE_DESCRIPTIONS[role_code],
                "is_active": True,
            },
        )
        roles.append(role)
    return roles
