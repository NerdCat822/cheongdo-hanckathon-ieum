from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from backend.catalog import MEMBER_IDS, SOURCE_IDS

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Category = Literal["benefit", "vaccination_checkup", "regular_visit"]
Status = Literal["확인 필요", "담당 요청", "진행 중", "완료", "해당 없음"]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def parse_date(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from None
    if parsed.isoformat() != value:
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
    return parsed


def validate_source(value):
    if value is not None and value not in SOURCE_IDS:
        raise ValueError("알 수 없는 시연 출처입니다.")
    return value


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TaskCreate(InputModel):
    title: Title
    description: Description
    category: Category
    due_date: date | None = None
    source_id: Identifier | None = None

    _date = field_validator("due_date", mode="before")(parse_date)
    _source = field_validator("source_id")(validate_source)


class TaskPatch(InputModel):
    title: Title | None = None
    description: Description | None = None
    category: Category | None = None
    due_date: date | None = None
    status: Status | None = None
    source_id: Identifier | None = None

    _date = field_validator("due_date", mode="before")(parse_date)
    _source = field_validator("source_id")(validate_source)

    @field_validator("title", "description", "category", "status", mode="before")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("이 항목은 비울 수 없습니다.")
        return value

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("수정할 항목이 필요합니다.")
        return self


class AssignmentRequest(InputModel):
    assignee_id: Identifier

    @field_validator("assignee_id")
    @classmethod
    def known_member(cls, value):
        if value not in MEMBER_IDS:
            raise ValueError("알 수 없는 가상 구성원입니다.")
        return value


class AssignmentResponse(InputModel):
    member_id: Identifier
    decision: Literal["accept", "reject", "adjust"]

    @field_validator("member_id")
    @classmethod
    def known_member(cls, value):
        if value not in MEMBER_IDS:
            raise ValueError("알 수 없는 가상 구성원입니다.")
        return value


class DraftRequest(InputModel):
    category: Category
    acknowledged: Literal[True]


class DraftItem(InputModel):
    title: Title
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1400)]
    uncertainty: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class DraftResult(InputModel):
    drafts: Annotated[list[DraftItem], Field(min_length=1, max_length=3)]


class HospitalSearch(InputModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class HospitalDetailRequest(InputModel):
    hospital_id: Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9+/=]+$")]
