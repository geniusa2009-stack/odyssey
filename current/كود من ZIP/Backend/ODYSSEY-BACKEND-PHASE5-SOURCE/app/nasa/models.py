"""NASA data provenance and provider result models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NASADataSource(BaseModel):
    """Attribution + provenance for every piece of external data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source_name: str
    dataset: str
    url: str | None = None
    retrieved_at: datetime | None = None
    license_notes: str
    variables_used: list[str]
    transformation_notes: str
    origin: Literal["fixture", "remote", "cache"] = "fixture"
    is_real_data: bool = Field(
        description="False for illustrative fixtures that only mimic a real format"
    )


class DataEnvelope[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: T
    source: NASADataSource
    from_cache: bool = False
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)


class TemperatureProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    site: str
    unit: Literal["K"] = "K"
    day_max: float | None
    night_min: float | None
    notes: str


class RadiationBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dose_equivalent_msv_per_hour: float
    location: str
    notes: str


class SpaceWeatherEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    event_type: Literal["SEP", "FLR", "CME"]
    event_time: str
    instruments: list[str] = Field(default_factory=list)
    link: str | None = None


class ReferenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    value: float
    unit: str
    evidence_id: str
