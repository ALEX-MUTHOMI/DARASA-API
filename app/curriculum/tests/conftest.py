from __future__ import annotations

import pathlib
import uuid

import pytest

from academics.models import AcademicYear, Cohort, GradeLevel, LearningArea
from core.models import CustomUser, Role, TenantUserRole
from curriculum.models import (
    CoreCompetency,
    CurriculumGradeMapping,
    CurriculumLearningArea,
    CurriculumSourceDocument,
    CurriculumStage,
    CurriculumValue,
    CurriculumVersion,
    KeyInquiryQuestion,
    LearningExperience,
    PertinentContemporaryIssue,
    SpecificLearningOutcome,
    Strand,
    SubStrand,
)
from tenant.models import School


@pytest.fixture
def app_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _token() -> str:
    return uuid.uuid4().hex[:10]


@pytest.fixture
def school() -> School:
    token = _token()
    return School.objects.create(
        name=f"Curriculum School {token}",
        schema_name=f"cur_{token}",
        subdomain=f"cur-{token}",
        school_code=f"CUR{token[:7]}".upper(),
    )


@pytest.fixture
def principal_role() -> Role:
    return Role.objects.create(
        code=Role.RoleCode.PRINCIPAL,
        name=Role.RoleCode.PRINCIPAL.label,
    )


@pytest.fixture
def teacher_role() -> Role:
    return Role.objects.create(
        code=Role.RoleCode.SUBJECT_TEACHER,
        name=Role.RoleCode.SUBJECT_TEACHER.label,
    )


@pytest.fixture
def principal_user(school, principal_role) -> CustomUser:
    user = CustomUser.objects.create_user(
        email=f"curriculum-principal-{_token()}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=principal_role)
    return user


@pytest.fixture
def teacher_user(school, teacher_role) -> CustomUser:
    user = CustomUser.objects.create_user(
        email=f"curriculum-teacher-{_token()}@example.test",
        password="test-only-secret",
    )
    TenantUserRole.objects.create(tenant=school, user=user, role=teacher_role)
    return user


@pytest.fixture
def grade_level() -> GradeLevel:
    return GradeLevel.objects.create(
        code=f"grade-{_token()}",
        name="Grade 4",
        stage=GradeLevel.Stage.PRIMARY,
    )


@pytest.fixture
def academic_year(school) -> AcademicYear:
    return AcademicYear.objects.create(
        tenant=school,
        label=f"AY-{_token()}",
        start_date="2026-01-01",
        end_date="2026-12-31",
    )


@pytest.fixture
def learning_area(school, grade_level) -> LearningArea:
    return LearningArea.objects.create(
        tenant=school,
        grade_level=grade_level,
        code=f"integrated-science-{_token()}",
        name="Integrated Science",
    )


@pytest.fixture
def cohort(school, academic_year, grade_level) -> Cohort:
    return Cohort.objects.create(
        tenant=school,
        academic_year=academic_year,
        grade_level=grade_level,
        name=f"North-{_token()}",
    )


@pytest.fixture
def source_document() -> CurriculumSourceDocument:
    return CurriculumSourceDocument.objects.create(
        source_authority=CurriculumSourceDocument.SourceAuthority.KICD,
        title="Official Grade 4 Curriculum Design Reference",
        document_code=f"KICD-{_token()}",
        source_url="https://kicd.ac.ke/cbc-materials/curriculum-designs/",
        document_version_label="2026-reference",
        checksum="sha256:phase4-test-checksum",
    )


@pytest.fixture
def curriculum_version(source_document) -> CurriculumVersion:
    return CurriculumVersion.objects.create(
        source_document=source_document,
        version_label=f"version-{_token()}",
        effective_from="2026-01-01",
        is_active=True,
    )


@pytest.fixture
def curriculum_stage() -> CurriculumStage:
    return CurriculumStage.objects.create(
        code=f"primary-{_token()}",
        name="Primary",
        description="Reference stage for CBE structure tests.",
    )


@pytest.fixture
def grade_mapping(grade_level, curriculum_stage, curriculum_version):
    return CurriculumGradeMapping.objects.create(
        grade_level=grade_level,
        curriculum_stage=curriculum_stage,
        curriculum_version=curriculum_version,
    )


@pytest.fixture
def curriculum_learning_area(curriculum_version, grade_level, learning_area):
    return CurriculumLearningArea.objects.create(
        curriculum_version=curriculum_version,
        grade_level=grade_level,
        learning_area=learning_area,
        official_name="Integrated Science",
        official_code=f"IS-{_token()}",
    )


@pytest.fixture
def strand(curriculum_learning_area) -> Strand:
    return Strand.objects.create(
        curriculum_learning_area=curriculum_learning_area,
        code=f"strand-{_token()}",
        title="Living Things",
        sequence_order=1,
    )


@pytest.fixture
def sub_strand(strand) -> SubStrand:
    return SubStrand.objects.create(
        strand=strand,
        code=f"substrand-{_token()}",
        title="Plants",
        sequence_order=1,
        suggested_time_allocation="6 lessons",
    )


@pytest.fixture
def learning_outcome(sub_strand) -> SpecificLearningOutcome:
    return SpecificLearningOutcome.objects.create(
        sub_strand=sub_strand,
        text="Identify observable plant features.",
        sequence_order=1,
    )


@pytest.fixture
def learning_experience(learning_outcome) -> LearningExperience:
    return LearningExperience.objects.create(
        learning_outcome=learning_outcome,
        text="Observe plants in the school compound.",
        sequence_order=1,
    )


@pytest.fixture
def key_inquiry_question(sub_strand) -> KeyInquiryQuestion:
    return KeyInquiryQuestion.objects.create(
        sub_strand=sub_strand,
        question_text="What features can we observe in plants?",
        sequence_order=1,
    )


@pytest.fixture
def core_competency() -> CoreCompetency:
    return CoreCompetency.objects.create(
        code=f"critical-thinking-{_token()}",
        name=f"Critical Thinking {_token()}",
    )


@pytest.fixture
def curriculum_value() -> CurriculumValue:
    return CurriculumValue.objects.create(
        code=f"responsibility-{_token()}",
        name=f"Responsibility {_token()}",
    )


@pytest.fixture
def pci() -> PertinentContemporaryIssue:
    return PertinentContemporaryIssue.objects.create(
        code=f"environment-{_token()}",
        name=f"Environmental Awareness {_token()}",
    )
