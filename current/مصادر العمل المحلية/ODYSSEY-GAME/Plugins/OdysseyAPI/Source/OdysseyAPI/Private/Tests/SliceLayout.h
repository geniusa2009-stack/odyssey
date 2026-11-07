// Test support: read the verification map definition
// (Content/Systems/Greybox/L_EarthCommand_Slice.layout.json) — the same data the editor greybox
// script builds the map from — so tests can check it against the registry, the backend's recorded
// bootstrap and the incident strategies.
#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/PresentationRules.h"

#include <map>
#include <set>
#include <string>
#include <vector>

namespace odyssey::tests
{

struct LayoutLight
{
	std::string label, follows, rule;
};

struct LayoutControl
{
	std::string object, action;
	std::map<std::string, std::string> params;
};

struct LayoutArea
{
	std::string id, location;  // location empty for Unreal-only space (Main Corridor)
	bool hasAnchor = false, hasZone = false;
	std::string anchorLabel;
	std::vector<std::pair<std::string, std::string>> systems;  // semantic id, actor label
	std::vector<LayoutLight> lights;
	std::vector<LayoutControl> controls;  // physical console controls (class "console")
};

struct SliceLayout
{
	bool ok = false;
	std::vector<std::string> allowedAreas;
	std::vector<LayoutArea> areas;
	std::map<std::string, presentation::LightRule> rules;
	std::vector<std::pair<std::string, std::string>> crew;  // id, label

	const LayoutArea* areaFor(const std::string& location) const
	{
		for (const LayoutArea& a : areas)
		{
			if (!location.empty() && a.location == location) return &a;
		}
		return nullptr;
	}
	// semantic id -> actor label for everything the map binds
	std::map<std::string, std::string> bindings() const
	{
		std::map<std::string, std::string> out;
		for (const LayoutArea& a : areas)
		{
			if (!a.location.empty()) out[a.location] = a.anchorLabel;
			for (const auto& s : a.systems) out[s.first] = s.second;
		}
		for (const auto& c : crew) out[c.first] = c.second;
		return out;
	}
	// A physical control that performs exactly this action (and params) on this object.
	bool hasControl(const std::string& objectId, const std::string& action, const std::map<std::string, std::string>& params) const
	{
		for (const LayoutArea& a : areas)
			for (const LayoutControl& c : a.controls)
				if (c.object == objectId && c.action == action && c.params == params) return true;
		return false;
	}
	std::vector<LayoutLight> lightsFollowing(const std::string& objectId) const
	{
		std::vector<LayoutLight> out;
		for (const LayoutArea& a : areas)
			for (const LayoutLight& l : a.lights)
				if (l.follows == objectId) out.push_back(l);
		return out;
	}
};

inline SliceLayout ParseSliceLayout(const json::Value& j)
{
	SliceLayout s;
	for (const json::Value& a : j["allowed_areas"].items()) s.allowedAreas.push_back(a.asString());
	for (const json::Value::Member& r : j["light_rules"].members()) s.rules[r.first] = presentation::ParseLightRule(r.second);
	for (const json::Value& a : j["areas"].items())
	{
		LayoutArea la;
		la.id = a["id"].asString();
		la.location = a["location"].isString() ? a["location"].asString() : std::string();
		la.hasAnchor = a["anchor"].isObject();
		la.hasZone = a["zone"].isObject();
		la.anchorLabel = a["anchor"]["label"].asString();
		for (const json::Value& sy : a["systems"].items())
		{
			la.systems.emplace_back(sy["id"].asString(), sy["label"].asString());
			for (const json::Value& c : sy["controls"].items())
			{
				LayoutControl lc;
				lc.object = sy["id"].asString();
				lc.action = c["action"].asString();
				for (const json::Value::Member& p : c["params"].members()) lc.params[p.first] = p.second.asString();
				la.controls.push_back(lc);
			}
		}
		for (const json::Value& l : a["lights"].items())
		{
			la.lights.push_back({l["label"].asString(), l["follows"].isString() ? l["follows"].asString() : std::string(),
				l["rule"].isString() ? l["rule"].asString() : std::string()});
		}
		s.areas.push_back(la);
	}
	for (const json::Value& c : j["crew"].items()) s.crew.emplace_back(c["id"].asString(), c["label"].asString());
	s.ok = !s.areas.empty() && !s.allowedAreas.empty();
	return s;
}

}  // namespace odyssey::tests
