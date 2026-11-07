











#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/StateMirror.h"
#include "OdysseyProtocol/Utility.h"

#include <map>
#include <string>

namespace odyssey::presentation
{

struct LightRule
{
	std::map<std::string, double> power, mode, status;  
	bool warning = false;  
};

inline double ScaleFor(const std::map<std::string, double>& table, const std::string& value)
{
	auto it = table.find(value);
	return it == table.end() ? 1.0 : it->second;
}

inline bool IncidentInvolves(const MirrorModel& model, const std::string& objectId)
{
	return detail::Any(model.activeIncidents(), [&](const IncidentInfo* incident) {
		return incident && detail::Any(incident->involvedObjects, [&](const std::string& candidate) {
			return candidate == objectId;
		});
	});
}


inline double Evaluate(const LightRule& r, const ObjectInfo& o, bool incidentActive)
{
	if (r.warning)
	{
		return incidentActive ? 1.0 : 0.0;
	}
	return ScaleFor(r.power, o.power) * ScaleFor(r.mode, o.mode) * ScaleFor(r.status, o.status);
}



inline double EvaluateIn(const LightRule& r, const MirrorModel& m, const std::string& objectId)
{
	const ObjectInfo* o = m.object(objectId);
	if (!o)
	{
		return r.warning ? 0.0 : 1.0;
	}
	return Evaluate(r, *o, IncidentInvolves(m, objectId));
}


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

}  
