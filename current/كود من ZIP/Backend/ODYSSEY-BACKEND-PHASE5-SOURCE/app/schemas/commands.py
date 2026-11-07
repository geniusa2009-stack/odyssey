"""Frozen command contracts of API v1 (docs/API_CONTRACT.md).

Decisions are referenced by ``option_id`` (from ``GET .../decision-options``), never by engine
internals. Every state-changing command carries ``expected_state_version``: a command based on
an older state is refused with ``409 STALE_STATE`` and never applied.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.read_models.decisions import OPTION_ID_PATTERN

OptionId = Annotated[str, Field(min_length=1, max_length=200, pattern=OPTION_ID_PATTERN)]
ParamName = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")]
MetaKey = Annotated[str, Field(min_length=1, max_length=64)]
Parameters = Annotated[dict[ParamName, float], Field(max_length=4)]
TimelineId = Annotated[str, Field(max_length=36, pattern=r"^[0-9a-fA-F\-]{1,36}$")]
ParticipantId = Annotated[str, Field(max_length=36)]


class _Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OptionRef(_Command):
    option_id: OptionId
    parameters: Parameters = Field(default_factory=dict)


class DecisionCommand(_Command):
    option_id: OptionId
    decision_type: str | None = Field(
        None, max_length=40, description="Optional: checked against the option's decision type"
    )
    parameters: Parameters = Field(default_factory=dict)
    expected_state_version: int = Field(
        ge=1, description="The state version the client based this command on (required)"
    )
    timeline_id: TimelineId | None = None
    participant_id: ParticipantId | None = None
    metadata: dict[MetaKey, str | int | float | bool] = Field(default_factory=dict, max_length=16)


class AdvanceCommand(_Command):
    ticks: int = Field(ge=1, le=240, description="Upper bound; the mission may conclude earlier")
    expected_state_version: int = Field(ge=1)
    timeline_id: TimelineId | None = None
    participant_id: ParticipantId | None = None


class CandidateCommand(_Command):
    label: str = Field(min_length=1, max_length=64)
    decisions: list[OptionRef] = Field(default_factory=list, max_length=8)


class FutureLensCommand(_Command):
    candidates: list[CandidateCommand] = Field(min_length=1, max_length=4)
    include_baseline: bool = True
    horizon_ticks: int = Field(24, ge=1, le=240)
    samples: int = Field(4, ge=1, le=16)
    prediction_mode: Literal["known_only", "omniscient"] = "known_only"
    timeline_id: TimelineId | None = None
    participant_id: ParticipantId | None = None


class BranchCommand(_Command):
    decision_id: str = Field(min_length=1, max_length=40)
    alternative: OptionRef | None = None
    continue_ticks: int = Field(0, ge=0, le=240)
    activate: bool = True
    label: str | None = Field(None, max_length=64)
    timeline_id: TimelineId | None = None
    participant_id: ParticipantId | None = None
