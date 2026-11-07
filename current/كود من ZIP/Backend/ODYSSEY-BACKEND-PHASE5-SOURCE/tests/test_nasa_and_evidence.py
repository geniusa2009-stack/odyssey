"""NASA provider architecture (fallback, cache, provenance) and the science evidence registry."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from app.nasa.cache import FileCache, InMemoryCache, RedisCache
from app.nasa.models import DataEnvelope, NASADataSource, SpaceWeatherEvent
from app.nasa.providers import (
    DataUnavailableError,
    DonkiSolarEnvironmentProvider,
    EvidenceReferenceProvider,
    FallbackSolarEnvironmentProvider,
    FixtureLunarEnvironmentProvider,
    FixtureSolarEnvironmentProvider,
    ProviderError,
    SolarEnvironmentProvider,
    UnavailableMarsProvider,
    all_sources,
)
from app.science.evidence import EvidenceNotFoundError, EvidenceRegistry, default_registry
from app.simulation.scenarios.loader import get_scenario

START, END = date(2024, 5, 1), date(2024, 5, 20)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Counting(SolarEnvironmentProvider):
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def sep_events(self, start: date, end: date) -> DataEnvelope[list[SpaceWeatherEvent]]:
        self.calls += 1
        if self.fail:
            raise ProviderError("network down")
        src = NASADataSource(
            id="t",
            source_name="t",
            dataset="t",
            license_notes="t",
            variables_used=[],
            transformation_notes="t",
            origin="remote",
            is_real_data=True,
        )
        return DataEnvelope(
            data=[
                SpaceWeatherEvent(event_id="E1", event_type="SEP", event_time="2024-05-02T00:00Z")
            ],
            source=src,
        )


class TestProviders:
    async def test_fixture_provider_is_flagged_synthetic(self) -> None:
        env = await FixtureSolarEnvironmentProvider().sep_events(START, END)
        assert env.source.is_real_data is False and env.source.origin == "fixture"
        assert env.warnings and len(env.data) == 2

    async def test_remote_disabled_uses_fixture_with_flag(self) -> None:
        chain = FallbackSolarEnvironmentProvider(
            None, FixtureSolarEnvironmentProvider(), InMemoryCache(), 60
        )
        env = await chain.sep_events(START, END)
        assert env.fallback_used and "disabled" in env.warnings[-1]

    async def test_outage_falls_back_without_breaking(self) -> None:
        primary = _Counting(fail=True)
        chain = FallbackSolarEnvironmentProvider(
            primary, FixtureSolarEnvironmentProvider(), InMemoryCache(), 60
        )
        env = await chain.sep_events(START, END)
        assert primary.calls == 1 and env.fallback_used
        assert "network down" in env.warnings[-1]

    async def test_successful_result_is_cached(self) -> None:
        primary = _Counting()
        chain = FallbackSolarEnvironmentProvider(
            primary, FixtureSolarEnvironmentProvider(), InMemoryCache(), 60
        )
        first = await chain.sep_events(START, END)
        second = await chain.sep_events(START, END)
        assert primary.calls == 1
        assert not first.from_cache and second.from_cache
        assert second.source.origin == "cache" and second.data == first.data

    async def test_donki_parsing_and_key_not_leaked(self) -> None:
        payload = [
            {
                "sepID": "2024-05-11T02:30:00-SEP-001",
                "eventTime": "2024-05-11T02:30Z",
                "instruments": [{"displayName": "GOES-P: SEISS"}],
                "link": "https://x",
            },
            {"sepID": None, "eventTime": "bad"},
            "garbage",
        ]

        def ok(request: httpx.Request) -> httpx.Response:
            assert request.url.params["api_key"] == "SECRETKEY"
            return httpx.Response(200, json=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(ok)) as client:
            env = await DonkiSolarEnvironmentProvider(
                client, "https://api.nasa.gov", "SECRETKEY"
            ).sep_events(START, END)
        assert [e.event_id for e in env.data] == ["2024-05-11T02:30:00-SEP-001"]
        assert env.source.is_real_data and env.source.retrieved_at is not None
        assert "SECRETKEY" not in env.model_dump_json()

        def boom(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
            with pytest.raises(ProviderError) as exc:
                await DonkiSolarEnvironmentProvider(
                    client, "https://api.nasa.gov", "SECRETKEY"
                ).sep_events(START, END)
        assert "SECRETKEY" not in str(exc.value)

    async def test_lunar_fixtures_and_unavailable_cases(self) -> None:
        lunar = FixtureLunarEnvironmentProvider()
        temp = await lunar.surface_temperature("equatorial")
        assert temp.data.day_max == 400.0 and temp.source.url
        rad = await lunar.radiation_baseline()
        assert rad.data.dose_equivalent_msv_per_hour == pytest.approx(0.057)
        with pytest.raises(DataUnavailableError):
            await lunar.surface_temperature("atlantis")
        with pytest.raises(DataUnavailableError):
            await UnavailableMarsProvider().surface_conditions(1)

    async def test_reference_values_from_evidence(self) -> None:
        provider = EvidenceReferenceProvider(default_registry())
        env = await provider.reference_values("oxygen")
        assert env.data and env.data[0].evidence_id == "bvad_o2_consumption"
        assert (await provider.get("bvad_o2_consumption")).value == pytest.approx(0.818)

    def test_every_source_has_provenance(self) -> None:
        for src in all_sources():
            assert src.source_name and src.dataset and src.license_notes
            assert src.variables_used and src.transformation_notes


class TestCaches:
    async def test_in_memory_ttl(self) -> None:
        clock = _Clock()
        cache = InMemoryCache(clock)
        await cache.set("k", {"a": 1}, 10)
        assert await cache.get("k") == {"a": 1}
        clock.now += 11
        assert await cache.get("k") is None

    async def test_file_cache_ttl_and_safe_names(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = FileCache(tmp_path, clock)
        await cache.set("../../etc/passwd", [1, 2], 5)
        assert [p.parent for p in tmp_path.iterdir()] == [tmp_path]
        assert await cache.get("../../etc/passwd") == [1, 2]
        clock.now += 6
        assert await cache.get("../../etc/passwd") is None
        (next(tmp_path.iterdir())).write_text("{corrupt")
        assert await cache.get("../../etc/passwd") is None

    @pytest.mark.redis
    async def test_redis_cache(self, redis_url: str) -> None:
        import redis.asyncio as aioredis

        client = aioredis.from_url(redis_url)
        try:
            cache = RedisCache(client, prefix="odyssey:test:")
            await cache.set("k", {"x": [1]}, 30)
            assert await cache.get("k") == {"x": [1]}
            assert await cache.get("missing") is None
        finally:
            await client.aclose()


class TestEvidenceRegistry:
    def test_registry_loads_and_is_well_formed(self) -> None:
        reg = default_registry()
        items = reg.all()
        assert len(items) >= 8
        assert [e.id for e in items] == sorted(e.id for e in items)
        for e in items:
            assert e.simulation_usage and e.simplification
            if e.verification_status != "unverified":
                # Verified claims link a source, except values derived from first principles.
                assert e.source_url is not None or "stoichiometry" in e.source_name.lower()

    def test_simulation_usage_points_at_real_scenario_config(self) -> None:
        data = get_scenario("luna-01").model_dump(mode="json", by_alias=True)
        for ev in default_registry().all():
            for usage in ev.simulation_usage:
                node: object = data
                for part in usage.split("."):
                    if isinstance(node, dict) and part in node:
                        node = node[part]
                    elif isinstance(node, list):  # list items are addressed by their id
                        node = next(
                            (i for i in node if isinstance(i, dict) and i.get("id") == part), None
                        )
                    else:
                        node = None
                    if node is None:
                        break
                assert node is not None, f"{ev.id}: {usage} not found in scenario"

    def test_lookup_errors_and_duplicates(self) -> None:
        reg = default_registry()
        with pytest.raises(EvidenceNotFoundError):
            reg.get("nope")
        item = reg.all()[0]
        with pytest.raises(ValueError, match="duplicate"):
            EvidenceRegistry([item, item])
        assert reg.for_usage(item.simulation_usage[0])
