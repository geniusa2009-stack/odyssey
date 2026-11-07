
#include "OdysseyEventRouter.h"

#include "OdysseyStringConv.h"

using namespace OdysseyConv;
using odyssey::json::Value;

namespace
{
TArray<FName> Names(const Value& Arr)
{
	TArray<FName> Out;
	for (const Value& V : Arr.items())
	{
		Out.Add(ToFName(V.asString()));
	}
	return Out;
}
}  

FOdysseyEventMeta UOdysseyEventRouter::MetaFrom(const Value& Env)
{
	FOdysseyEventMeta M;
	M.Type = ToFName(Env["type"].asString());
	M.Scope = ToFName(Env["scope"].asString());
	M.Seq = Env["seq"].asInt();
	M.StateVersion = Env["state_version"].asInt();
	M.SimTick = Env["sim_tick"].asInt();
	return M;
}

void UOdysseyEventRouter::Route(const odyssey::Notice& N)
{
	using odyssey::NoticeKind;
	if (N.kind == NoticeKind::SnapshotApplied)
	{
		OnSnapshotApplied.Broadcast(ToFName(N.detail));
		return;
	}
	if (N.kind == NoticeKind::InfoEvent || N.kind == NoticeKind::EventApplied)
	{
		if (N.detail == "object.refreshed")
		{
			for (const std::string& Id : N.ids)
			{
				OnInteractionsRefreshed.Broadcast(ToFName(Id));
			}
			return;
		}
		RouteEvent(N.detail, N.data, N.ids);
	}
}

void UOdysseyEventRouter::RouteEvent(const std::string& T, const Value& Env, const std::vector<std::string>& Ids)
{
	const FOdysseyEventMeta Meta = MetaFrom(Env);
	const Value& P = Env["payload"];
	LastSeq = FMath::Max(LastSeq, Meta.Seq);
	LastType = Meta.Type;
	bool bRouted = true;

	if (T == "system.state_changed" || T == "infrastructure.changed")
	{
		FOdysseySystemStateEvent E{Meta, ToFName(P["object"].asString())};
		for (const Value::Member& Ch : P["changes"].members())
		{
			E.ChangedFields.Add(ToFName(Ch.first));
		}
		OnSystemStateChanged.Broadcast(E);
	}
	else if (T == "incident.started" || T == "incident.updated" || T == "incident.resolved")
	{
		FOdysseyIncidentEvent E;
		E.Meta = Meta;
		E.IncidentId = ToFName(P["incident"].asString());
		E.Stage = ToFName(P["stage"].asString());
		E.bResolved = T == "incident.resolved";
		E.InvolvedObjects = Names(P["involved_objects"]);
		E.InvolvedCrew = Names(P["involved_crew"]);
		OnIncident.Broadcast(E);
	}
	else if (T == "world.access_changed")
	{
		const std::string& Id = P["object"].isString() ? P["object"].asString() : P["location"].asString();
		OnAccessChanged.Broadcast(FOdysseyAccessEvent{Meta, ToFName(Id), ToFName(P["access"].asString())});
	}
	else if (T == "inventory.changed" || T == "cargo.changed")
	{
		OnInventoryChanged.Broadcast(FOdysseyInventoryEvent{Meta, ToFName(P["container"].asString())});
	}
	else if (T == "objective.updated")
	{
		OnObjectiveUpdated.Broadcast(FOdysseyObjectiveEvent{Meta, ToFName(P["objective"].asString()), ToFName(P["status"].asString())});
	}
	else if (T == "resource.threshold_changed" || T == "system.alert_changed")
	{
		OnAlertChanged.Broadcast(FOdysseyAlertEvent{Meta, ToFName(P["alert"].asString()), P["active"].asBool(),
			ToFName(P["severity"].asString()), ToFName(P["category"].asString())});
	}
	else if (T == "mission.updated")
	{
		OnMissionUpdated.Broadcast(FOdysseyMissionEvent{Meta, ToFName(P["status"].asString()), ToFName(P["simulation_status"].asString())});
	}
	else if (T == "clock.updated")
	{
		OnClockUpdated.Broadcast(FOdysseyClockEvent{Meta, ToFName(P["mode"].asString()), ToFName(P["pause_reason"].asString()),
			static_cast<float>(P["ticks_per_second"].asDouble())});
	}
	else if (T == "crew.updated")
	{
		OnCrewUpdated.Broadcast(FOdysseyCrewEvent{Meta, ToFName(P["id"].asString())});
	}
	else if (T == "crew.cue")
	{
		FOdysseyCueEvent E;
		E.Meta = Meta;
		E.Cue = ToFName(P["cue"].asString());
		E.Speaker = ToFName(P["speaker"].asString());
		E.Line = ToFString(P["line"].asString());
		E.MessageKey = ToFName(P["message_key"].asString());
		E.Priority = static_cast<int32>(P["priority"].asInt());
		OnCrewCue.Broadcast(E);
	}
	else if (T == "capability.progressed")
	{
		OnCapabilityProgressed.Broadcast(FOdysseyProgressEvent{Meta, ToFName(P["capability"].asString()), ToFName(P["stage"].asString())});
	}
	else if (T == "certification.granted")
	{
		OnCertificationGranted.Broadcast(FOdysseyProgressEvent{Meta, ToFName(P["certification"].asString()), NAME_None});
	}
	else if (T == "discovery.recorded" || T == "knowledge.unlocked")
	{
		const std::string& Id = T == "discovery.recorded" ? P["discovery"].asString() : P["insight"].asString();
		OnKnowledge.Broadcast(FOdysseyProgressEvent{Meta, ToFName(Id), ToFName(T)});
	}
	else if (T == "future_lens.ready")
	{
		OnFutureLensReady.Broadcast(FOdysseyInfoEvent{Meta, ToFName(Env["timeline_id"].asString())});
	}
	else if (T == "black_box.ready")
	{
		OnBlackBoxReady.Broadcast(FOdysseyInfoEvent{Meta, ToFName(P["timeline_id"].isString() ? P["timeline_id"].asString() : Env["timeline_id"].asString())});
	}
	else if (T == "checkpoint.saved")
	{
		OnCheckpointSaved.Broadcast(FOdysseyInfoEvent{Meta, ToFName(Env["timeline_id"].asString())});
	}
	else
	{
		
		
		
		bRouted = T == "mission.transitioned" || T == "timeline.changed" || T == "campaign.updated" ||
				  T == "time.advanced" || T == "interactions.changed" || T == "world.object_revealed";
	}
	Routed += bRouted ? 1 : 0;
	Unrouted += bRouted ? 0 : 1;
	if (!Ids.empty())
	{
		TArray<FName> Changed;
		for (const std::string& Id : Ids)
		{
			Changed.Add(ToFName(Id));
		}
		OnSemanticIdsChanged.Broadcast(Changed);
	}
}
