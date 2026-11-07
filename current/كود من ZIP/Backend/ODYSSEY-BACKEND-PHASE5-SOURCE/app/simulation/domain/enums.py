"""Enumerations shared by the simulation domain."""

from __future__ import annotations

from enum import StrEnum


class CrewRole(StrEnum):
    """Crew roles. Values double as the multiplayer mission roles (see MissionRole)."""

    COMMANDER = "commander"
    POWER_ENGINEER = "power_engineer"
    LIFE_SUPPORT = "life_support"
    SCIENCE_OFFICER = "science_officer"


class CrewLocation(StrEnum):
    HABITAT = "habitat"
    SHELTER = "shelter"
    EVA = "eva"


class SubsystemMode(StrEnum):
    OFF = "off"
    ECO = "eco"
    NOMINAL = "nominal"
    BOOST = "boost"


class MissionStatus(StrEnum):
    ACTIVE = "active"
    CONCLUDED = "concluded"


class RoverStatus(StrEnum):
    DOCKED = "docked"
    TRAVERSING = "traversing"
    RETURNING = "returning"
    STOWED = "stowed"
    LOST = "lost"


class OpportunityStatus(StrEnum):
    OPEN = "open"
    ACTIVE = "active"
    COMPLETED = "completed"
    MISSED = "missed"


class ObjectiveStatus(StrEnum):
    PENDING = "pending"
    ACHIEVED = "achieved"
    FAILED = "failed"


class AlertSeverity(StrEnum):
    CAUTION = "caution"
    WARNING = "warning"
    CRITICAL = "critical"


class ProvenanceKind(StrEnum):
    """What put a value into the state. Used by root-cause tracing."""

    SCENARIO = "scenario"
    DECISION = "decision"
    EVENT = "event"
    ENGINE = "engine"


class EventKind(StrEnum):
    """Kinds of events emitted by the engine (scenario events and engine-generated)."""

    SCHEDULED = "scheduled"
    STATE_TRIGGERED = "state_triggered"
    DECISION_TRIGGERED = "decision_triggered"
    RANDOM = "random"
    ENVIRONMENTAL = "environmental"
    SYSTEM_FAULT = "system_fault"
    MILESTONE = "milestone"
    SCIENCE_OPPORTUNITY = "science_opportunity"
    COMMUNICATION = "communication"
    SPACE_WEATHER = "space_weather"
    RESOURCE_WARNING = "resource_warning"
    CASCADE_WARNING = "cascade_warning"
    ALERT_RAISED = "alert_raised"
    ALERT_CLEARED = "alert_cleared"
    PHASE_CHANGE = "phase_change"
    OBJECTIVE = "objective"
    OUTCOME = "outcome"
    MAINTENANCE = "maintenance"
    DECISION_APPLIED = "decision_applied"
    ROVER = "rover"
