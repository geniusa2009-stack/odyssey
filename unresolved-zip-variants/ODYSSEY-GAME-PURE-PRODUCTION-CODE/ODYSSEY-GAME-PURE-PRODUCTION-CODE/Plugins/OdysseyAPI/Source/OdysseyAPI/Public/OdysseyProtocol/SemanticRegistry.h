






#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/StateMirror.h"

#include <map>
#include <set>
#include <string>
#include <vector>

namespace odyssey
{

enum class SemanticKind : uint8_t
{
	Location,
	Object,
	Container,
	Crew,
	Unknown
};

inline SemanticKind ParseSemanticKind(const std::string& s)
{
	if (s == "location") return SemanticKind::Location;
	if (s == "object") return SemanticKind::Object;
	if (s == "container") return SemanticKind::Container;
	if (s == "crew") return SemanticKind::Crew;
	return SemanticKind::Unknown;
}

struct SemanticEntry
{
	std::string id;
	SemanticKind kind = SemanticKind::Unknown;
	std::string world;     
	std::string name;      
	std::string location;  
	std::string binding;   
	bool requiredInSlice = false;  
};

class SemanticRegistry
{
public:
	
	
	
	
	bool Load(const json::Value& rows, std::string* error = nullptr)
	{
		entries_.clear();
		if (!rows.isArray())
		{
			if (error)
			{
				*error = "registry_not_an_array";
			}
			return false;
		}
		for (const json::Value& e : rows.items())
		{
			SemanticEntry se;
			se.id = e["Id"].asString();
			se.kind = ParseSemanticKind(e["Kind"].asString());
			se.world = e["World"].asString();
			se.name = e["DisplayName"].asString();
			se.location = e["Location"].asString();
			se.binding = e["Binding"].asString();
			se.requiredInSlice = e["RequiredInSlice"].asBool();
			if (se.id.empty() || se.kind == SemanticKind::Unknown || entries_.count(se.id) ||
				e["Name"].asString() != se.id)
			{
				if (error)
				{
					*error = "invalid_or_duplicate_entry:" + se.id;
				}
				return false;
			}
			entries_.emplace(se.id, se);
		}
		return true;
	}

	void Add(const SemanticEntry& e) { entries_[e.id] = e; }

	const SemanticEntry* Find(const std::string& id) const
	{
		auto it = entries_.find(id);
		return it == entries_.end() ? nullptr : &it->second;
	}

	
	
	const SemanticEntry* Resolve(const std::string& id)
	{
		const SemanticEntry* e = Find(id);
		if (!e && !id.empty())
		{
			unknown_.insert(id);
		}
		return e;
	}
	const std::set<std::string>& unknownIds() const { return unknown_; }

	size_t size() const { return entries_.size(); }
	std::vector<const SemanticEntry*> All() const
	{
		std::vector<const SemanticEntry*> out;
		for (const auto& kv : entries_)
		{
			out.push_back(&kv.second);
		}
		return out;
	}

	
	std::vector<std::string> UnknownInSnapshot(const MirrorModel& m) const
	{
		std::vector<std::string> out;
		auto visit = [&](const std::string& id) {
			if (!id.empty() && !Find(id))
			{
				out.push_back(id);
			}
		};
		for (const LocationInfo& l : m.locations) visit(l.id);
		for (const ObjectInfo& o : m.objects) visit(o.id);
		for (const ContainerInfo& c : m.containers) visit(c.id);
		for (const CrewInfo& c : m.crew) visit(c.id);
		return out;
	}

	
	std::vector<std::string> UnboundRequired() const
	{
		std::vector<std::string> out;
		for (const auto& kv : entries_)
		{
			if (kv.second.requiredInSlice && kv.second.binding.empty())
			{
				out.push_back(kv.first);
			}
		}
		return out;
	}

private:
	std::map<std::string, SemanticEntry> entries_;
	std::set<std::string> unknown_;
};

}  
