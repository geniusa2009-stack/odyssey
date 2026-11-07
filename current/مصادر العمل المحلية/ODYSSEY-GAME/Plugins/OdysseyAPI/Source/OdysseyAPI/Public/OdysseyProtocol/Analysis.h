// ODYSSEY protocol core — typed models for Future Lens and Black Box responses.
//
// Data ingestion only (Phase 6): the debug viewers render these; the final Future Lens visuals
// and the 3D Black Box room come later. Fields follow app/game/contracts/analysis.py.
#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"

#include <string>
#include <vector>

namespace odyssey
{

struct LensWorldHint
{
	std::string object, field, now, after;
};

struct LensResource
{
	std::string metric, label, unit, warningLevel;
	double start = 0, end = 0, delta = 0, worst = 0;
	bool hasVsBaseline = false;
	double vsBaseline = 0;
};

struct LensBranch
{
	std::string id, action, target;
	bool isBaseline = false, valid = false, affectsSimulation = false, concludesWithinHorizon = false;
	std::string rejectionReason, rejectionMessage, projectedOutcomeTier;
	std::vector<std::string> affectedObjects;
	std::vector<LensWorldHint> worldHints;
	std::vector<LensResource> resources;
	std::vector<std::pair<std::string, std::string>> objectives;  // objective -> projected status
	std::vector<std::string> warnings;                             // alert ids
	std::string confidenceLevel;
	double confidenceScore = 0, riskEnd = 0, riskPeak = 0;
};

struct FutureLensModel
{
	bool ok = false;
	std::string error;
	std::string timelineId, missionId, predictionMode;
	int64_t stateVersion = 0, baseTick = 0, requestedTicks = 0, projectedTicks = 0;
	double horizonHours = 0;
	bool anticipatesUnforeseeable = true;
	std::vector<LensBranch> branches;
};

inline FutureLensModel ParseFutureLens(const json::Value& j)
{
	FutureLensModel m;
	const ProtocolCheck pc = CheckProtocol(j);
	if (!pc.ok)
	{
		m.error = pc.reason;
		return m;
	}
	m.timelineId = j["timeline_id"].asString();
	m.missionId = j["mission_id"].asString();
	m.stateVersion = j["state_version"].asInt();
	m.baseTick = j["base_tick"].asInt();
	m.requestedTicks = j["horizon"]["requested_ticks"].asInt();
	m.projectedTicks = j["horizon"]["projected_ticks"].asInt();
	m.horizonHours = j["horizon"]["hours"].asDouble();
	m.predictionMode = j["knowledge_boundary"]["prediction_mode"].asString();
	m.anticipatesUnforeseeable = j["knowledge_boundary"]["anticipates_unforeseeable_events"].asBool(true);
	for (const json::Value& b : j["branches"].items())
	{
		LensBranch lb;
		lb.id = b["id"].asString();
		lb.action = b["action"].asString();
		lb.target = b["target"].asString();
		lb.isBaseline = b["is_baseline"].asBool();
		lb.valid = b["valid"].asBool();
		lb.affectsSimulation = b["affects_simulation"].asBool();
		lb.concludesWithinHorizon = b["concludes_within_horizon"].asBool();
		lb.rejectionReason = b["rejection"]["reason"].asString();
		lb.rejectionMessage = b["rejection"]["message"].asString();
		lb.projectedOutcomeTier = b["projected_outcome_tier"].asString();
		for (const json::Value& o : b["affected_objects"].items())
		{
			lb.affectedObjects.push_back(o.asString());
		}
		for (const json::Value& h : b["world_hints"].items())
		{
			lb.worldHints.push_back(
				{h["object"].asString(), h["field"].asString(), h["now"].asString(), h["after"].asString()});
		}
		for (const json::Value& r : b["resources"].items())
		{
			LensResource lr;
			lr.metric = r["metric"].asString();
			lr.label = r["label"].asString();
			lr.unit = r["unit"].asString();
			lr.warningLevel = r["warning_level"].asString();
			lr.start = r["start"].asDouble();
			lr.end = r["end"].asDouble();
			lr.delta = r["delta"].asDouble();
			lr.worst = r["worst"].asDouble();
			lr.hasVsBaseline = r["vs_baseline"].isNumber();
			lr.vsBaseline = r["vs_baseline"].asDouble();
			lb.resources.push_back(lr);
		}
		for (const json::Value& o : b["objectives"].items())
		{
			lb.objectives.emplace_back(o["objective"].asString(), o["projected_status"].asString());
		}
		for (const json::Value& w : b["warnings"].items())
		{
			lb.warnings.push_back(w["alert"].asString());
		}
		lb.confidenceLevel = b["confidence"]["level"].asString();
		lb.confidenceScore = b["confidence"]["score"].asDouble();
		lb.riskEnd = b["risk"]["end_index"].asDouble();
		lb.riskPeak = b["risk"]["peak_index"].asDouble();
		m.branches.push_back(lb);
	}
	m.ok = true;
	return m;
}

struct CausalNodeModel
{
	std::string id, type, label, systemRef, objectiveRef, anchor, severity;
	bool hasTick = false;
	int64_t simTick = 0;
	double simHours = 0;
	std::string commandId, action, target, counterfactual;
};

struct CausalEdgeModel
{
	std::string source, target, relation;
};

struct BlackBoxModel
{
	bool ok = false;
	std::string error;
	std::string timelineId, missionId, missionStatus, simulationStatus, outcomeCode, outcomeTier, statement;
	int64_t finalTick = 0;
	bool counterfactualsEvaluated = false;
	std::vector<CausalNodeModel> nodes;
	std::vector<CausalEdgeModel> edges;

	const CausalNodeModel* node(const std::string& id) const
	{
		for (const CausalNodeModel& n : nodes)
		{
			if (n.id == id)
			{
				return &n;
			}
		}
		return nullptr;
	}
	// Every edge references existing nodes (a viewer can lay the graph out safely).
	bool edgesResolve() const
	{
		for (const CausalEdgeModel& e : edges)
		{
			if (!node(e.source) || !node(e.target))
			{
				return false;
			}
		}
		return true;
	}
};

inline BlackBoxModel ParseBlackBox(const json::Value& j)
{
	BlackBoxModel m;
	const ProtocolCheck pc = CheckProtocol(j);
	if (!pc.ok)
	{
		m.error = pc.reason;
		return m;
	}
	m.timelineId = j["timeline_id"].asString();
	m.missionId = j["mission_id"].asString();
	m.missionStatus = j["mission_status"].asString();
	m.simulationStatus = j["simulation_status"].asString();
	m.finalTick = j["final_tick"].asInt();
	m.counterfactualsEvaluated = j["counterfactuals_evaluated"].asBool();
	m.outcomeCode = j["outcome"]["code"].asString();
	m.outcomeTier = j["outcome"]["tier"].asString();
	m.statement = j["statement"].asString();
	for (const json::Value& n : j["nodes"].items())
	{
		CausalNodeModel c;
		c.id = n["id"].asString();
		c.type = n["type"].asString();
		c.label = n["label"].asString();
		c.systemRef = n["system_ref"].asString();
		c.objectiveRef = n["objective_ref"].asString();
		c.anchor = n["anchor"].asString();
		c.severity = n["severity"].asString();
		c.hasTick = n["sim_tick"].isNumber();
		c.simTick = n["sim_tick"].asInt();
		c.simHours = n["sim_time_hours"].asDouble();
		c.commandId = n["decision"]["command_id"].asString();
		c.action = n["decision"]["action"].asString();
		c.target = n["decision"]["target"].asString();
		c.counterfactual = n["decision"]["counterfactual"].asString();
		m.nodes.push_back(c);
	}
	for (const json::Value& e : j["edges"].items())
	{
		m.edges.push_back({e["source"].asString(), e["target"].asString(), e["relation"].asString()});
	}
	m.ok = true;
	return m;
}

}  // namespace odyssey
