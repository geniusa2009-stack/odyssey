







#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"
#include "OdysseyProtocol/Utility.h"

#include <algorithm>
#include <cstdint>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace odyssey
{

struct InteractionInfo
{
	std::string action;
	bool available = false;
	std::string reason;  
	std::vector<std::pair<std::string, std::vector<std::string>>> params;  
};

struct ModuleInfo
{
	std::string slot;
	std::string item;
	std::string state;
};

struct ObjectInfo
{
	std::string id, kind, name, location, parent;
	bool critical = false;
	std::string access, status, power, mode, infrastructureState;
	bool inspected = false;
	bool hasCharge = false;
	double chargeKwh = 0.0;
	std::vector<std::string> tags;
	std::vector<InteractionInfo> interactions;
	std::vector<ModuleInfo> modules;
	bool interactionsStale = false;  

	const InteractionInfo* interaction(const std::string& action) const
	{
		for (const InteractionInfo& i : interactions)
		{
			if (i.action == action)
			{
				return &i;
			}
		}
		return nullptr;
	}
};

struct LocationInfo
{
	std::string id, name, region, kind, access;
	bool visited = false;
};

struct IncidentInfo
{
	std::string id, messageKey, stage;
	int64_t startedTick = 0;
	bool resolved = false;
	int64_t resolvedTick = 0;
	std::vector<std::string> involvedObjects, involvedCrew, facts;
};

struct ObjectiveInfo
{
	std::string id, category, status, messageKey;
	bool required = false;
};

struct ResourceInfo
{
	std::string id, label, unit, state, warningState;
	double value = 0.0;
};

struct AlertInfo
{
	std::string id, severity, category;
};

struct RequirementInfo
{
	std::string id, reason;
	bool met = false;
};

struct AuthorizationInfo
{
	bool present = false;
	std::string gate, target;
	bool available = false, authorized = false;
	std::vector<RequirementInfo> requirements;
};

struct CrewInfo
{
	std::string id, name, role, specialty, intent, location, healthBand;
	std::vector<std::string> involvedIncidents;
};

struct CueInfo
{
	std::string cue, speaker, line, messageKey;
	int64_t priority = 0, tick = 0;
};

struct ItemStack
{
	std::string item;
	int64_t quantity = 0;
	double massKg = 0.0;
};

struct ContainerInfo
{
	std::string id, name, location, role, vehicle;
	double massKg = 0.0;
	bool hasMassLimit = false;
	double massLimitKg = 0.0;
	std::vector<ItemStack> items;
};

struct ClockInfo
{
	std::string mode, pauseReason;
	bool started = false;
	int64_t simTick = 0, maxTicks = 0;
	double tickHours = 0.0, ticksPerSecond = 0.0, elapsedHours = 0.0;
};

struct PhaseInfo
{
	std::string id, title, status;
	int64_t order = 0;
	bool authored = false;
};

struct CapabilityInfo
{
	std::string id, stage;  
};

struct MirrorModel
{
	bool loaded = false;
	std::string sessionId, sessionStatus, contentVersion;
	std::string timelineId, timelineStatus;
	int64_t timelineAttempt = 0;
	int64_t stateVersion = 0;
	int64_t lastSeq = 0;
	std::string missionId, missionTitle, missionStatus, simulationStatus, outcomeTier, completion;
	std::string playerLocation;
	ClockInfo clock;
	AuthorizationInfo authorization;
	std::vector<LocationInfo> locations;
	std::vector<ObjectInfo> objects;
	std::vector<ContainerInfo> containers;
	std::vector<IncidentInfo> incidents;
	std::vector<ObjectiveInfo> objectives;
	std::vector<ResourceInfo> resources;
	std::vector<AlertInfo> alerts;
	std::vector<CrewInfo> crew;
	std::vector<CueInfo> recentCues;
	std::vector<PhaseInfo> phases;
	std::vector<CapabilityInfo> capabilities;
	std::vector<std::string> certifications, discoveries, insights;
	std::string activeMission;

	template <typename T>
	static const T* findIn(const std::vector<T>& values, const std::string& id)
	{
		return detail::FindById(values, id);
	}
	template <typename T>
	static T* findIn(std::vector<T>& values, const std::string& id)
	{
		return detail::FindById(values, id);
	}
	const ObjectInfo* object(const std::string& id) const { return findIn(objects, id); }
	const LocationInfo* location(const std::string& id) const { return findIn(locations, id); }
	const IncidentInfo* incident(const std::string& id) const { return findIn(incidents, id); }
	const ContainerInfo* container(const std::string& id) const { return findIn(containers, id); }
	const CrewInfo* crewMember(const std::string& id) const { return findIn(crew, id); }
	
	std::string activePhase() const
	{
		const PhaseInfo* best = nullptr;
		for (const PhaseInfo& p : phases)
		{
			if (p.status == "active" && (!best || p.order < best->order))
			{
				best = &p;
			}
		}
		return best ? best->id : std::string();
	}
	std::vector<const IncidentInfo*> activeIncidents() const
	{
		std::vector<const IncidentInfo*> out;
		for (const IncidentInfo& i : incidents)
		{
			if (!i.resolved)
			{
				out.push_back(&i);
			}
		}
		return out;
	}
};


struct MirrorDelta
{
	std::string type;
	bool applied = false;     
	bool unknownType = false; 
	bool needsSnapshot = false;
	std::string snapshotReason;
	std::vector<std::string> refreshObjects;  
	std::vector<std::string> changedIds;      
	bool resourcesStale = false;              
};

namespace mirror_detail
{
inline std::vector<std::string> strings(const json::Value& arr)
{
	std::vector<std::string> out;
	for (const json::Value& v : arr.items())
	{
		out.push_back(v.asString());
	}
	return out;
}

inline InteractionInfo parseInteraction(const json::Value& j)
{
	InteractionInfo i;
	i.action = j["action"].asString();
	i.available = j["available"].asBool();
	i.reason = j["reason"].asString();
	for (const json::Value::Member& m : j["params"].members())
	{
		i.params.emplace_back(m.first, strings(m.second));
	}
	return i;
}

inline std::vector<ModuleInfo> parseModules(const json::Value& arr)
{
	std::vector<ModuleInfo> out;
	for (const json::Value& m : arr.items())
	{
		out.push_back({m["slot"].asString(), m["item"].asString(), m["state"].asString()});
	}
	return out;
}

inline ObjectInfo parseObject(const json::Value& j)
{
	ObjectInfo o;
	o.id = j["id"].asString();
	o.kind = j["kind"].asString();
	o.name = j["name"].asString();
	o.location = j["location"].asString();
	o.parent = j["parent"].asString();
	o.critical = j["critical"].asBool();
	o.access = j["access"].asString();
	o.inspected = j["inspected"].asBool();
	o.status = j["status"].asString();
	o.power = j["power"].asString();
	o.mode = j["mode"].asString();
	o.infrastructureState = j["infrastructure_state"].asString();
	o.hasCharge = j["charge_kwh"].isNumber();
	o.chargeKwh = j["charge_kwh"].asDouble();
	o.tags = strings(j["tags"]);
	for (const json::Value& i : j["interactions"].items())
	{
		o.interactions.push_back(parseInteraction(i));
	}
	o.modules = parseModules(j["modules"]);
	return o;
}

inline ContainerInfo parseContainer(const json::Value& j)
{
	ContainerInfo c;
	c.id = j["id"].asString();
	c.name = j["name"].asString();
	c.location = j["location"].asString();
	c.role = j["role"].asString();
	c.vehicle = j["vehicle"].asString();
	c.massKg = j["mass_kg"].asDouble();
	c.hasMassLimit = j["mass_limit_kg"].isNumber();
	c.massLimitKg = j["mass_limit_kg"].asDouble();
	for (const json::Value& it : j["items"].items())
	{
		c.items.push_back({it["item"].asString(), it["quantity"].asInt(), it["mass_kg"].asDouble()});
	}
	return c;
}

inline IncidentInfo parseIncident(const json::Value& j)
{
	IncidentInfo i;
	i.id = j["id"].isString() ? j["id"].asString() : j["incident"].asString();
	i.messageKey = j["message_key"].asString();
	i.stage = j["stage"].asString();
	i.startedTick = j["started_tick"].asInt();
	i.resolved = j["resolved_tick"].isNumber();
	i.resolvedTick = j["resolved_tick"].asInt();
	i.involvedObjects = strings(j["involved_objects"]);
	i.involvedCrew = strings(j["involved_crew"]);
	i.facts = strings(j["facts"]);
	return i;
}

inline CrewInfo parseCrew(const json::Value& j)
{
	CrewInfo c;
	c.id = j["id"].asString();
	c.name = j["name"].asString();
	c.role = j["role"].asString();
	c.specialty = j["specialty"].asString();
	c.intent = j["intent"].asString();
	c.location = j["location"].asString();
	c.healthBand = j["health_band"].asString();
	c.involvedIncidents = strings(j["involved_incidents"]);
	return c;
}

inline CueInfo parseCue(const json::Value& j)
{
	CueInfo c;
	c.cue = j["cue"].asString();
	c.speaker = j["speaker"].asString();
	c.line = j["line"].asString();
	c.messageKey = j["message_key"].asString();
	c.priority = j["priority"].asInt();
	c.tick = j["tick"].asInt();
	return c;
}

inline AuthorizationInfo parseAuthorization(const json::Value& j)
{
	AuthorizationInfo a;
	if (!j.isObject())
	{
		return a;
	}
	a.present = true;
	a.gate = j["gate"].asString();
	a.target = j["target"].asString();
	a.available = j["available"].asBool();
	a.authorized = j["authorized"].asBool();
	for (const json::Value& r : j["requirements"].items())
	{
		a.requirements.push_back({r["id"].asString(), r["reason"].asString(), r["met"].asBool()});
	}
	return a;
}

inline void addUnique(std::vector<std::string>& v, const std::string& s)
{
	if (!s.empty() && std::find(v.begin(), v.end(), s) == v.end())
	{
		v.push_back(s);
	}
}
}  

class StateMirror
{
public:
	static constexpr size_t kMaxCues = 8;

	const MirrorModel& model() const { return m_; }
	uint64_t unknownEventsIgnored() const { return unknown_; }

	
	bool LoadSnapshot(const json::Value& s, std::string* error = nullptr)
	{
		using namespace mirror_detail;
		const ProtocolCheck pc = CheckProtocol(s);
		if (!pc.ok)
		{
			if (error)
			{
				*error = pc.reason;
			}
			return false;
		}
		MirrorModel m;
		m.loaded = true;
		const json::Value& sess = s["session"];
		m.sessionId = sess["id"].asString();
		m.sessionStatus = sess["status"].asString();
		m.contentVersion = sess["content_version"].asString();
		m.lastSeq = sess["last_seq"].asInt();
		m.stateVersion = s["state_version"].asInt();
		const json::Value& tl = s["timeline"];
		m.timelineId = tl["id"].asString();
		m.timelineStatus = tl["status"].asString();
		m.timelineAttempt = tl["attempt"].asInt();
		const json::Value& mission = s["mission"];
		m.missionId = mission["id"].asString();
		m.missionTitle = mission["title"].asString();
		m.missionStatus = mission["status"].asString();
		m.simulationStatus = mission["simulation_status"].asString();
		m.outcomeTier = mission["outcome_tier"].asString();
		m.completion = mission["completion"].asString();
		m.authorization = parseAuthorization(mission["authorization"]);
		for (const json::Value& o : mission["objectives"].items())
		{
			m.objectives.push_back({o["id"].asString(), o["category"].asString(), o["status"].asString(),
				o["message_key"].asString(), o["required"].asBool()});
		}
		for (const json::Value& r : mission["resources"].items())
		{
			ResourceInfo ri;
			ri.id = r["id"].asString();
			ri.label = r["label"].asString();
			ri.unit = r["unit"].asString();
			ri.state = r["state"].asString();
			ri.warningState = r["warning_state"].asString();
			ri.value = r["value"].asDouble();
			m.resources.push_back(ri);
		}
		for (const json::Value& a : mission["alerts"].items())
		{
			m.alerts.push_back({a["id"].asString(), a["severity"].asString(), a["category"].asString()});
		}
		const json::Value& c = s["clock"];
		m.clock.mode = c["mode"].asString();
		m.clock.pauseReason = c["pause_reason"].asString();
		m.clock.started = c["started"].asBool();
		m.clock.simTick = c["sim_tick"].asInt();
		m.clock.maxTicks = c["max_ticks"].asInt();
		m.clock.tickHours = c["tick_hours"].asDouble();
		m.clock.ticksPerSecond = c["ticks_per_second"].asDouble();
		m.clock.elapsedHours = c["elapsed_hours"].asDouble();
		const json::Value& w = s["world"];
		m.playerLocation = w["player_location"].asString();
		for (const json::Value& l : w["locations"].items())
		{
			LocationInfo li;
			li.id = l["id"].asString();
			li.name = l["name"].asString();
			li.region = l["region"].asString();
			li.kind = l["kind"].asString();
			li.access = l["access"].asString();
			li.visited = l["visited"].asBool();
			m.locations.push_back(li);
		}
		for (const json::Value& o : w["objects"].items())
		{
			m.objects.push_back(parseObject(o));
		}
		for (const json::Value& ct : w["containers"].items())
		{
			m.containers.push_back(parseContainer(ct));
		}
		for (const json::Value& i : w["incidents"].items())
		{
			m.incidents.push_back(parseIncident(i));
		}
		for (const json::Value& cr : w["crew"].items())
		{
			m.crew.push_back(parseCrew(cr));
		}
		for (const json::Value& cue : w["recent_cues"].items())
		{
			m.recentCues.push_back(parseCue(cue));
		}
		const json::Value& camp = s["campaign"];
		m.activeMission = camp["active_mission"].asString();
		for (const json::Value& p : camp["phases"].items())
		{
			PhaseInfo pi;
			pi.id = p["id"].asString();
			pi.title = p["title"].asString();
			pi.status = p["status"].asString();
			pi.order = p["order"].asInt();
			pi.authored = p["authored"].asBool();
			m.phases.push_back(pi);
		}
		for (const json::Value& cap : camp["capabilities"].items())
		{
			m.capabilities.push_back({cap["id"].asString(), cap["stage"].asString()});
		}
		m.certifications = strings(camp["certifications"]);
		for (const json::Value& d : s["discoveries"].items())
		{
			m.discoveries.push_back(d["id"].asString());
		}
		for (const json::Value& i : s["insights"].items())
		{
			m.insights.push_back(i["id"].asString());
		}
		m_ = std::move(m);
		return true;
	}

	
	void ApplyObjectDetail(const json::Value& objectView)
	{
		ObjectInfo fresh = mirror_detail::parseObject(objectView);
		if (ObjectInfo* o = MirrorModel::findIn(m_.objects, fresh.id))
		{
			*o = std::move(fresh);
		}
		else
		{
			m_.objects.push_back(std::move(fresh));
		}
	}

	
	MirrorDelta ApplyEvent(const json::Value& env)
	{
		using namespace mirror_detail;
		MirrorDelta d;
		d.type = env["type"].asString();
		const json::Value& p = env["payload"];
		m_.lastSeq = std::max(m_.lastSeq, env["seq"].asInt());
		m_.stateVersion = std::max(m_.stateVersion, env["state_version"].asInt());
		if (!env["timeline_id"].asString().empty() && env["timeline_id"].asString() != m_.timelineId &&
			d.type != "mission.transitioned" && d.type != "timeline.changed")
		{
			d.needsSnapshot = true;
			d.snapshotReason = "timeline_mismatch";
			return d;
		}
		const std::string& t = d.type;
		
		
		if (p["snapshot_required"].isBool() && p["snapshot_required"].asBool())
		{
			d.needsSnapshot = true;
			d.snapshotReason = t;
			return d;
		}
		if (t == "system.state_changed" || t == "infrastructure.changed")
		{
			const std::string id = p["object"].asString();
			ObjectInfo* o = MirrorModel::findIn(m_.objects, id);
			if (!o)
			{
				d.refreshObjects.push_back(id);
				return d;
			}
			for (const json::Value::Member& ch : p["changes"].members())
			{
				const std::string& f = ch.first;
				if (f == "access") o->access = ch.second.asString();
				else if (f == "inspected") o->inspected = ch.second.asBool();
				else if (f == "status") o->status = ch.second.asString();
				else if (f == "power") o->power = ch.second.asString();
				else if (f == "mode") o->mode = ch.second.asString();
				else if (f == "infrastructure_state") o->infrastructureState = ch.second.asString();
				else if (f == "modules") o->modules = parseModules(ch.second);
			}
			d.applied = true;
			d.changedIds.push_back(id);
		}
		else if (t == "world.access_changed")
		{
			if (p.has("object"))
			{
				if (ObjectInfo* o = MirrorModel::findIn(m_.objects, p["object"].asString()))
				{
					o->access = p["access"].asString();
				}
				d.changedIds.push_back(p["object"].asString());
			}
			else if (LocationInfo* l = MirrorModel::findIn(m_.locations, p["location"].asString()))
			{
				l->access = p["access"].asString();
				d.changedIds.push_back(l->id);
			}
			d.applied = true;
		}
		else if (t == "world.object_revealed")
		{
			d.refreshObjects.push_back(p["object"].asString());
		}
		else if (t == "interactions.changed")
		{
			for (const std::string& id : strings(p["objects"]))
			{
				if (ObjectInfo* o = MirrorModel::findIn(m_.objects, id))
				{
					o->interactionsStale = true;
				}
				d.refreshObjects.push_back(id);
			}
			d.applied = true;
		}
		else if (t == "inventory.changed" || t == "cargo.changed")
		{
			const std::string id = p["container"].asString();
			ContainerInfo* c = MirrorModel::findIn(m_.containers, id);
			if (!c)
			{
				d.needsSnapshot = true;
				d.snapshotReason = "unknown_container";
				return d;
			}
			c->items.clear();
			for (const json::Value& it : p["items"].items())
			{
				c->items.push_back({it["item"].asString(), it["quantity"].asInt(), it["mass_kg"].asDouble()});
			}
			c->massKg = p["mass_kg"].asDouble();
			d.applied = true;
			d.changedIds.push_back(id);
		}
		else if (t == "incident.started" || t == "incident.updated" || t == "incident.resolved")
		{
			const std::string id = p["incident"].asString();
			IncidentInfo* inc = MirrorModel::findIn(m_.incidents, id);
			if (!inc)
			{
				IncidentInfo fresh = parseIncident(p);
				fresh.startedTick = env["sim_tick"].asInt();
				m_.incidents.push_back(fresh);
				inc = &m_.incidents.back();
			}
			inc->stage = p["stage"].asString();
			if (p.has("facts"))
			{
				inc->facts = strings(p["facts"]);
			}
			if (t == "incident.resolved")
			{
				inc->resolved = true;
				inc->resolvedTick = env["sim_tick"].asInt();
			}
			d.applied = true;
			d.changedIds.push_back(id);
		}
		else if (t == "objective.updated")
		{
			if (ObjectiveInfo* o = MirrorModel::findIn(m_.objectives, p["objective"].asString()))
			{
				o->status = p["status"].asString();
			}
			d.applied = true;
			d.changedIds.push_back(p["objective"].asString());
		}
		else if (t == "resource.threshold_changed" || t == "system.alert_changed")
		{
			const std::string id = p["alert"].asString();
			m_.alerts.erase(std::remove_if(m_.alerts.begin(), m_.alerts.end(),
								[&id](const AlertInfo& a) { return a.id == id; }),
				m_.alerts.end());
			if (p["active"].asBool())
			{
				m_.alerts.push_back({id, p["severity"].asString(), p["category"].asString()});
			}
			d.applied = true;
			d.resourcesStale = true;
			d.changedIds.push_back(id);
		}
		else if (t == "mission.updated")
		{
			m_.missionStatus = p["status"].asString();
			m_.simulationStatus = p["simulation_status"].asString();
			m_.outcomeTier = p["outcome_tier"].asString();
			m_.authorization = parseAuthorization(p["authorization"]);
			d.applied = true;
			d.changedIds.push_back(m_.missionId);
		}
		else if (t == "time.advanced")
		{
			m_.clock.simTick = p["to_tick"].asInt();
			m_.clock.elapsedHours = p["elapsed_hours"].asDouble();
			d.applied = true;
			d.resourcesStale = true;
		}
		else if (t == "clock.updated")
		{
			m_.clock.mode = p["mode"].asString();
			m_.clock.pauseReason = p["pause_reason"].asString();
			m_.clock.ticksPerSecond = p["ticks_per_second"].asDouble();
			m_.clock.simTick = p["sim_tick"].asInt();
			
			m_.clock.started = m_.clock.started || m_.clock.pauseReason != "not_started";
			d.applied = true;
		}
		else if (t == "crew.updated")
		{
			CrewInfo fresh = parseCrew(p);
			if (CrewInfo* c = MirrorModel::findIn(m_.crew, fresh.id))
			{
				*c = fresh;
			}
			else
			{
				m_.crew.push_back(fresh);
			}
			d.applied = true;
			d.changedIds.push_back(fresh.id);
		}
		else if (t == "crew.cue")
		{
			m_.recentCues.push_back(parseCue(p));
			if (m_.recentCues.size() > kMaxCues)
			{
				m_.recentCues.erase(m_.recentCues.begin());
			}
			d.applied = true;
			d.changedIds.push_back(p["speaker"].asString());
		}
		else if (t == "capability.progressed")
		{
			const std::string id = p["capability"].asString();
			if (CapabilityInfo* c = MirrorModel::findIn(m_.capabilities, id))
			{
				c->stage = p["stage"].asString();
			}
			else
			{
				m_.capabilities.push_back({id, p["stage"].asString()});
			}
			d.applied = true;
			d.changedIds.push_back(id);
		}
		else if (t == "certification.granted")
		{
			addUnique(m_.certifications, p["certification"].asString());
			d.applied = true;
			d.changedIds.push_back(p["certification"].asString());
		}
		else if (t == "campaign.updated")
		{
			for (const json::Value::Member& ph : p["phases"].members())
			{
				if (PhaseInfo* pi = MirrorModel::findIn(m_.phases, ph.first))
				{
					pi->status = ph.second.asString();
				}
			}
			m_.activeMission = p["active_mission"].asString();
			d.applied = true;
		}
		else if (t == "discovery.recorded")
		{
			addUnique(m_.discoveries, p["discovery"].asString());
			d.applied = true;
			d.changedIds.push_back(p["discovery"].asString());
		}
		else if (t == "knowledge.unlocked")
		{
			addUnique(m_.insights, p["insight"].asString());
			d.applied = true;
			d.changedIds.push_back(p["insight"].asString());
		}
		else if (t == "mission.transitioned" || t == "timeline.changed")
		{
			d.needsSnapshot = true;
			d.snapshotReason = t;
		}
		else if (t == "checkpoint.saved" || t == "future_lens.ready" || t == "black_box.ready")
		{
			d.applied = false;  
		}
		else
		{
			d.unknownType = true;
			++unknown_;
		}
		return d;
	}

private:
	MirrorModel m_;
	uint64_t unknown_ = 0;
};

}  
