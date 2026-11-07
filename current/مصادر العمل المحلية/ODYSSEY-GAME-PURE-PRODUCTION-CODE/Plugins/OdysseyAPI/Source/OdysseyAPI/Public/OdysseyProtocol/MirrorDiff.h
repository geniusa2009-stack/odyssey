






#pragma once

#include "OdysseyProtocol/StateMirror.h"

#include <cmath>
#include <string>
#include <vector>

namespace odyssey
{

struct MirrorDiffOptions
{
	bool compareResources = false;
};

inline std::vector<std::string> DiffMirrors(const MirrorModel& local, const MirrorModel& server,
	const MirrorDiffOptions& opt = MirrorDiffOptions())
{
	std::vector<std::string> d;
	auto eq = [&](const std::string& what, const std::string& a, const std::string& b) {
		if (a != b) d.push_back(what + ": local '" + a + "' server '" + b + "'");
	};
	auto eqi = [&](const std::string& what, int64_t a, int64_t b) {
		if (a != b) d.push_back(what + ": local " + std::to_string(a) + " server " + std::to_string(b));
	};
	auto eqb = [&](const std::string& what, bool a, bool b) {
		if (a != b) d.push_back(what + ": local " + (a ? "true" : "false") + " server " + (b ? "true" : "false"));
	};
	eqi("state_version", local.stateVersion, server.stateVersion);
	eqi("last_seq", local.lastSeq, server.lastSeq);
	eq("timeline", local.timelineId, server.timelineId);
	eq("mission", local.missionId, server.missionId);
	eq("mission.status", local.missionStatus, server.missionStatus);
	eq("player_location", local.playerLocation, server.playerLocation);
	eq("clock.mode", local.clock.mode, server.clock.mode);
	eqi("clock.sim_tick", local.clock.simTick, server.clock.simTick);
	eqb("clock.started", local.clock.started, server.clock.started);
	eq("active_phase", local.activePhase(), server.activePhase());
	for (const LocationInfo& s : server.locations)
	{
		const LocationInfo* l = local.location(s.id);
		if (!l) { d.push_back("location missing: " + s.id); continue; }
		eq(s.id + ".access", l->access, s.access);
		eqb(s.id + ".visited", l->visited, s.visited);
	}
	eqi("objects.count", static_cast<int64_t>(local.objects.size()), static_cast<int64_t>(server.objects.size()));
	for (const ObjectInfo& s : server.objects)
	{
		const ObjectInfo* l = local.object(s.id);
		if (!l) { d.push_back("object missing: " + s.id); continue; }
		eq(s.id + ".status", l->status, s.status);
		eq(s.id + ".access", l->access, s.access);
		eq(s.id + ".power", l->power, s.power);
		eq(s.id + ".mode", l->mode, s.mode);
		eq(s.id + ".infrastructure_state", l->infrastructureState, s.infrastructureState);
		eqb(s.id + ".inspected", l->inspected, s.inspected);
		eqb(s.id + ".interactions_stale", l->interactionsStale, false);
		if (opt.compareResources && l->hasCharge && std::fabs(l->chargeKwh - s.chargeKwh) > 1e-6)
		{
			d.push_back(s.id + ".charge_kwh differs");
		}
		eqi(s.id + ".interactions.count", static_cast<int64_t>(l->interactions.size()), static_cast<int64_t>(s.interactions.size()));
		for (const InteractionInfo& si : s.interactions)
		{
			const InteractionInfo* li = l->interaction(si.action);
			if (!li) { d.push_back(s.id + " interaction missing: " + si.action); continue; }
			eqb(s.id + "." + si.action + ".available", li->available, si.available);
			eq(s.id + "." + si.action + ".reason", li->reason, si.reason);
		}
		eqi(s.id + ".modules.count", static_cast<int64_t>(l->modules.size()), static_cast<int64_t>(s.modules.size()));
	}
	for (const ContainerInfo& s : server.containers)
	{
		const ContainerInfo* l = local.container(s.id);
		if (!l) { d.push_back("container missing: " + s.id); continue; }
		eqi(s.id + ".stacks", static_cast<int64_t>(l->items.size()), static_cast<int64_t>(s.items.size()));
		for (size_t i = 0; i < s.items.size() && i < l->items.size(); ++i)
		{
			eq(s.id + ".item", l->items[i].item, s.items[i].item);
			eqi(s.id + "." + s.items[i].item, l->items[i].quantity, s.items[i].quantity);
		}
	}
	eqi("incidents.count", static_cast<int64_t>(local.incidents.size()), static_cast<int64_t>(server.incidents.size()));
	for (const IncidentInfo& s : server.incidents)
	{
		const IncidentInfo* l = local.incident(s.id);
		if (!l) { d.push_back("incident missing: " + s.id); continue; }
		eq(s.id + ".stage", l->stage, s.stage);
		eqb(s.id + ".resolved", l->resolved, s.resolved);
	}
	for (const ObjectiveInfo& s : server.objectives)
	{
		const ObjectiveInfo* l = MirrorModel::findIn(local.objectives, s.id);
		if (!l) { d.push_back("objective missing: " + s.id); continue; }
		eq(s.id + ".status", l->status, s.status);
	}
	eqb("authorization.present", local.authorization.present, server.authorization.present);
	eqb("authorization.available", local.authorization.available, server.authorization.available);
	for (const RequirementInfo& s : server.authorization.requirements)
	{
		const RequirementInfo* l = MirrorModel::findIn(local.authorization.requirements, s.id);
		if (!l) { d.push_back("requirement missing: " + s.id); continue; }
		eqb(s.id + ".met", l->met, s.met);
	}
	for (const CrewInfo& s : server.crew)
	{
		const CrewInfo* l = local.crewMember(s.id);
		if (!l) { d.push_back("crew missing: " + s.id); continue; }
		eq(s.id + ".location", l->location, s.location);
	}
	for (const PhaseInfo& s : server.phases)
	{
		const PhaseInfo* l = MirrorModel::findIn(local.phases, s.id);
		if (!l) { d.push_back("phase missing: " + s.id); continue; }
		eq(s.id + ".status", l->status, s.status);
	}
	eqi("certifications", static_cast<int64_t>(local.certifications.size()), static_cast<int64_t>(server.certifications.size()));
	if (opt.compareResources)
	{
		for (const ResourceInfo& s : server.resources)
		{
			const ResourceInfo* l = MirrorModel::findIn(local.resources, s.id);
			if (!l) { d.push_back("resource missing: " + s.id); continue; }
			if (std::fabs(l->value - s.value) > 1e-6) d.push_back(s.id + " value differs");
		}
	}
	return d;
}

}  
