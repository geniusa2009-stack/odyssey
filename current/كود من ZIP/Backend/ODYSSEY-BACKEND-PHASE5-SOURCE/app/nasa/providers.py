"""NASA-derived data provider interfaces and implementations.

Design rules:
* The simulation never calls providers. Providers feed scenario authoring, evidence and
  explanations; scenarios hold the (versioned) numbers the engine uses.
* Every result is wrapped in a :class:`DataEnvelope` carrying :class:`NASADataSource`
  provenance.
* Remote access is optional and off by default. Any remote failure falls back to cache, then to
  local fixtures, flagged with ``fallback_used`` — external data failure never breaks the game.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.nasa.cache import CacheBackend
from app.nasa.models import (
    DataEnvelope,
    NASADataSource,
    RadiationBaseline,
    ReferenceValue,
    SpaceWeatherEvent,
    TemperatureProfile,
)
from app.science.evidence import EvidenceRegistry, ScienceEvidence

log = logging.getLogger(__name__)
FIXTURES = Path(__file__).parent / "fixtures"


class ProviderError(RuntimeError):
    pass


class DataUnavailableError(ProviderError):
    """The provider has no data for this request (not an outage)."""


# ------------------------------------------------------------------------------------------
# Interfaces
# ------------------------------------------------------------------------------------------


class LunarEnvironmentProvider(ABC):
    @abstractmethod
    async def surface_temperature(self, site: str) -> DataEnvelope[TemperatureProfile]: ...

    @abstractmethod
    async def radiation_baseline(self) -> DataEnvelope[RadiationBaseline]: ...


class SolarEnvironmentProvider(ABC):
    @abstractmethod
    async def sep_events(self, start: date, end: date) -> DataEnvelope[list[SpaceWeatherEvent]]: ...


class MarsEnvironmentProvider(ABC):
    """Reserved for future Mars scenarios; no Mars dataset has been selected yet."""

    @abstractmethod
    async def surface_conditions(self, sol: int) -> DataEnvelope[dict[str, Any]]: ...


class MissionReferenceProvider(ABC):
    @abstractmethod
    async def reference_values(self, topic: str) -> DataEnvelope[list[ReferenceValue]]: ...


class ScienceEvidenceProvider(ABC):
    @abstractmethod
    async def get(self, evidence_id: str) -> ScienceEvidence: ...

    @abstractmethod
    async def list(self) -> list[ScienceEvidence]: ...


# ------------------------------------------------------------------------------------------
# Sources
# ------------------------------------------------------------------------------------------

DIVINER_SOURCE = NASADataSource(
    id="lro_diviner_summary",
    source_name="LRO Diviner Lunar Radiometer Experiment (UCLA / NASA)",
    dataset="Published summary surface temperatures",
    url="https://www.diviner.ucla.edu/science",
    retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
    license_notes="Values quoted from public mission science pages; cite LRO/Diviner team.",
    variables_used=[
        "equatorial noon temperature",
        "equatorial night temperature",
        "polar cold-trap temperature",
    ],
    transformation_notes="Rounded summary values; not a gridded data product.",
    origin="fixture",
    is_real_data=True,
)

LND_SOURCE = NASADataSource(
    id="change4_lnd",
    source_name="Chang'E-4 Lunar Lander Neutrons and Dosimetry (Zhang et al. 2020)",
    dataset="Surface dose equivalent rate (Science Advances 6(39) eaaz1334)",
    url="https://doi.org/10.1126/sciadv.aaz1334",
    retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
    license_notes="Published peer-reviewed value; non-NASA mission. Cite the paper.",
    variables_used=["dose equivalent rate"],
    transformation_notes="1369 µSv/day converted to 0.057 mSv/h.",
    origin="fixture",
    is_real_data=True,
)

DONKI_SAMPLE_SOURCE = NASADataSource(
    id="donki_sep_sample",
    source_name="NASA DONKI (format only)",
    dataset="DONKI SEP — SYNTHETIC SAMPLE",
    url="https://api.nasa.gov/DONKI/SEP",
    retrieved_at=None,
    license_notes="Synthetic placeholder mimicking the DONKI response shape. NOT real events.",
    variables_used=["sepID", "eventTime", "instruments"],
    transformation_notes="Parsed into SpaceWeatherEvent.",
    origin="fixture",
    is_real_data=False,
)


def _parse_sep(raw: list[dict[str, Any]]) -> list[SpaceWeatherEvent]:
    events: list[SpaceWeatherEvent] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("sepID") or not item.get("eventTime"):
            continue
        instruments = [
            str(i.get("displayName"))
            for i in item.get("instruments") or []
            if isinstance(i, dict) and i.get("displayName")
        ]
        events.append(
            SpaceWeatherEvent(
                event_id=str(item["sepID"]),
                event_type="SEP",
                event_time=str(item["eventTime"]),
                instruments=instruments,
                link=item.get("link") or None,
            )
        )
    return events


# ------------------------------------------------------------------------------------------
# Fixture implementations (offline, deterministic)
# ------------------------------------------------------------------------------------------


class FixtureLunarEnvironmentProvider(LunarEnvironmentProvider):
    _SITES = {
        "equatorial": TemperatureProfile(
            site="equatorial",
            day_max=400.0,
            night_min=100.0,
            notes="Diviner: ~400 K at noon, below 100 K at night",
        ),
        "polar_cold_trap": TemperatureProfile(
            site="polar_cold_trap",
            day_max=None,
            night_min=25.0,
            notes="Diviner: permanently shadowed craters as cold as ~25 K",
        ),
    }

    async def surface_temperature(self, site: str) -> DataEnvelope[TemperatureProfile]:
        profile = self._SITES.get(site)
        if profile is None:
            raise DataUnavailableError(f"no temperature fixture for site '{site}'")
        return DataEnvelope(data=profile, source=DIVINER_SOURCE)

    async def radiation_baseline(self) -> DataEnvelope[RadiationBaseline]:
        return DataEnvelope(
            data=RadiationBaseline(
                dose_equivalent_msv_per_hour=0.057,
                location="Von Kármán crater (far side)",
                notes="1369 µSv/day measured by Chang'E-4 LND",
            ),
            source=LND_SOURCE,
        )


class FixtureSolarEnvironmentProvider(SolarEnvironmentProvider):
    def __init__(self, path: Path = FIXTURES / "donki_sep_sample.json") -> None:
        self._path = path

    async def sep_events(self, start: date, end: date) -> DataEnvelope[list[SpaceWeatherEvent]]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return DataEnvelope(
            data=_parse_sep(raw.get("events", [])),
            source=DONKI_SAMPLE_SOURCE,
            warnings=["Synthetic sample data, not real space weather events."],
        )


class UnavailableMarsProvider(MarsEnvironmentProvider):
    async def surface_conditions(self, sol: int) -> DataEnvelope[dict[str, Any]]:
        raise DataUnavailableError("no Mars dataset selected (see docs/NASA_DATA_OPTIONS.md)")


class EvidenceReferenceProvider(MissionReferenceProvider, ScienceEvidenceProvider):
    """Reference values and evidence served from the local evidence registry."""

    def __init__(self, registry: EvidenceRegistry) -> None:
        self._registry = registry

    async def reference_values(self, topic: str) -> DataEnvelope[list[ReferenceValue]]:
        values = [
            ReferenceValue(key=e.id, value=e.value, unit=e.unit or "", evidence_id=e.id)
            for e in self._registry.all()
            if e.value is not None and topic.lower() in e.concept.lower()
        ]
        source = NASADataSource(
            id=f"evidence:{topic}",
            source_name="ODYSSEY science evidence registry",
            dataset="app/science/data/evidence.yaml",
            license_notes="See each evidence item.",
            variables_used=[v.key for v in values],
            transformation_notes="Values as recorded in the registry.",
            origin="fixture",
            is_real_data=True,
        )
        return DataEnvelope(data=values, source=source)

    async def get(self, evidence_id: str) -> ScienceEvidence:
        return self._registry.get(evidence_id)

    async def list(self) -> list[ScienceEvidence]:
        return self._registry.all()


# ------------------------------------------------------------------------------------------
# Remote implementation (optional) + fallback chain
# ------------------------------------------------------------------------------------------


class DonkiSolarEnvironmentProvider(SolarEnvironmentProvider):
    """Live DONKI SEP catalogue. Requires network and an API key from settings."""

    def __init__(
        self, client: httpx.AsyncClient, base_url: str, api_key: str, timeout_seconds: float = 10.0
    ) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._timeout = timeout_seconds

    async def sep_events(self, start: date, end: date) -> DataEnvelope[list[SpaceWeatherEvent]]:
        try:
            resp = await self._client.get(
                f"{self._base}/DONKI/SEP",
                params={
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "api_key": self._key,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            raw = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never log the request URL: it contains the API key.
            raise ProviderError(f"DONKI request failed: {type(exc).__name__}") from None
        if not isinstance(raw, list):
            raise ProviderError("unexpected DONKI response shape")
        source = NASADataSource(
            id="donki_sep_live",
            source_name="NASA DONKI (CCMC)",
            dataset="DONKI SEP",
            url=f"{self._base}/DONKI/SEP",
            retrieved_at=datetime.now(UTC),
            license_notes="NASA open API; cite NASA CCMC DONKI.",
            variables_used=["sepID", "eventTime", "instruments", "link"],
            transformation_notes="Parsed into SpaceWeatherEvent; malformed entries dropped.",
            origin="remote",
            is_real_data=True,
        )
        return DataEnvelope(data=_parse_sep(raw), source=source)


class FallbackSolarEnvironmentProvider(SolarEnvironmentProvider):
    """cache → primary → (store) ; on failure → fallback fixture (flagged)."""

    def __init__(
        self,
        primary: SolarEnvironmentProvider | None,
        fallback: SolarEnvironmentProvider,
        cache: CacheBackend,
        ttl_seconds: int,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._cache = cache
        self._ttl = ttl_seconds

    async def sep_events(self, start: date, end: date) -> DataEnvelope[list[SpaceWeatherEvent]]:
        key = f"sep:{start.isoformat()}:{end.isoformat()}"
        cached = await self._cache.get(key)
        if cached is not None:
            env = DataEnvelope[list[SpaceWeatherEvent]].model_validate(cached)
            env.from_cache = True
            env.source = env.source.model_copy(update={"origin": "cache"})
            return env
        if self._primary is not None:
            try:
                env = await self._primary.sep_events(start, end)
                await self._cache.set(key, env.model_dump(mode="json"), self._ttl)
                return env
            except ProviderError as exc:
                log.warning(
                    "nasa_provider_fallback",
                    extra={"error_code": "provider_error", "detail": str(exc)},
                )
                env = await self._fallback.sep_events(start, end)
                env.fallback_used = True
                env.warnings.append(f"Live data unavailable ({exc}); using local fixture.")
                return env
        env = await self._fallback.sep_events(start, end)
        env.fallback_used = True
        env.warnings.append("Remote NASA data disabled; using local fixture.")
        return env


def all_sources() -> list[NASADataSource]:
    return [DIVINER_SOURCE, LND_SOURCE, DONKI_SAMPLE_SOURCE]
