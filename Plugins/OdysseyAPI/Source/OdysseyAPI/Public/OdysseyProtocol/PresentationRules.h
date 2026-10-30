// ODYSSEY protocol core — how world lights follow authoritative object state.
//
// Presentation only: a light's intensity scale is a pure function of what the BACKEND reports for
// one object (power / mode / status, and whether an active incident involves it). Nothing here
// decides an outcome; the same function runs in Unreal (UOdysseyObjectPresentationComponent) and
// in the native tests / live harness, which evaluate the real map definition against real backend
// state (Content/Systems/Greybox/L_EarthCommand_Slice.layout.json).
//
// Backend vocabulary (verified against 4f7be83): power powered|off, mode off|eco|nominal|boost,
// status operational|offline|damaged. Restoring a shed load (mode → nominal) returns all three to
// powered/nominal/operational, so a rule evaluates back to 1.0 by construction — the world
// returns to its correct state because it is always recomputed from the backend's values.
#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/StateMirror.h"

#include <map>
#include <string>

namespace odyssey::presentation
{

struct LightRule
{
	std::map<std::string, double> power, mode, status;  // value -> intensity multiplier; unlisted = 1
	bool warning = false;  // on (1) while an active incident involves the object, else off (0)
};

inline double ScaleFor(const std::map<std::string, double>& table, const std::string& value)
{
	auto it = table.find(value);
	return it == table.end() ? 1.0 : it->second;
}

inline bool IncidentInvolves(const MirrorModel& m, const std::string& objectId)
{
	for (const IncidentInfo* inc : m.activeIncidents())
	{
		for (const std::string& o : inc->involvedObjects)
		{
			if (o == objectId)
			{
				return true;
			}
		}
	}
	return false;
}

// Intensity multiplier in [0, 1] for a light that follows `o`.
inline double Evaluate(const LightRule& r, const ObjectInfo& o, bool incidentActive)
{
	if (r.warning)
	{
		return incidentActive ? 1.0 : 0.0;
	}
	return ScaleFor(r.power, o.power) * ScaleFor(r.mode, o.mode) * ScaleFor(r.status, o.status);
}

// Convenience: evaluate against the mirror; an object the backend has not revealed keeps the
// authored look (1.0, or off for warning lights).
inline double EvaluateIn(const LightRule& r, const MirrorModel& m, const std::string& objectId)
{
	const ObjectInfo* o = m.object(objectId);
	if (!o)
	{
		return r.warning ? 0.0 : 1.0;
	}
	return Evaluate(r, *o, IncidentInvolves(m, objectId));
}

// Rule JSON (layout file): {"power": {"off": 0.35}, "mode": {"eco": 0.75}, "status": {}, "warning": false}
inline LightRule ParseLightRule(const json::Value& j)
{
	LightRule r;
	auto table = [](const json::Value& t, std::map<std::string, double>& out) {
		for (const json::Value::Member& m : t.members())
		{
			out[m.first] = m.second.asDouble();
		}
	};
	table(j["power"], r.power);
	table(j["mode"], r.mode);
	table(j["status"], r.status);
	r.warning = j["warning"].asBool();
	return r;
}

}  // namespace odyssey::presentation
