// Test support: a deliberately small JSON-Schema validator for the subset the odyssey.game.v1
// OpenAPI document uses (components/$ref, type, anyOf, properties, required,
// additionalProperties, maxProperties, min/maxLength, minimum, const, enum, items, pattern).
// Patterns are matched through the contract's own id validators; an unknown pattern is an error,
// so a new backend pattern is noticed instead of silently accepted.
#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"

#include <string>
#include <vector>

namespace odyssey::tests
{

inline bool MatchKnownPattern(const std::string& pattern, const std::string& s, bool& known)
{
	known = true;
	if (pattern == "^[A-Za-z0-9_.:\\-]{1,128}$") return IsValidId(s, 1, 128);
	if (pattern == "^[A-Za-z0-9_.:\\-]{8,128}$") return IsValidId(s, 8, 128);
	if (pattern == "^[a-z_]+\\.[a-z_]+$") return IsValidActionType(s);
	if (pattern == "^gs_[a-z2-7]{20,32}$") return IsValidPublicId(s, "gs_");
	if (pattern == "^gt_[a-z2-7]{20,32}$") return IsValidPublicId(s, "gt_");
	if (pattern == "^[a-z0-9_\\-]{1,32}$")
	{
		if (s.empty() || s.size() > 32) return false;
		for (char c : s)
		{
			if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
		}
		return true;
	}
	known = false;
	return false;
}

class SchemaValidator
{
public:
	explicit SchemaValidator(const json::Value& openapi) : components_(openapi["components"]["schemas"]) {}

	bool Validate(const json::Value& value, const std::string& schemaName, std::vector<std::string>& errors) const
	{
		const json::Value* s = components_.find(schemaName);
		if (!s)
		{
			errors.push_back("unknown schema " + schemaName);
			return false;
		}
		const size_t before = errors.size();
		validateNode(value, *s, schemaName, errors, 0);
		return errors.size() == before;
	}

	const json::Value* Schema(const std::string& name) const { return components_.find(name); }

	// Does `schemaName` (following $ref/anyOf) declare property `field`?
	bool HasProperty(const std::string& schemaName, const std::string& field) const
	{
		const json::Value* s = components_.find(schemaName);
		return s && (*s)["properties"].has(field);
	}

private:
	const json::Value& components_;

	const json::Value& resolve(const json::Value& s) const
	{
		const std::string& ref = s["$ref"].asString();
		const std::string prefix = "#/components/schemas/";
		if (ref.rfind(prefix, 0) == 0)
		{
			return components_[ref.substr(prefix.size())];
		}
		return s;
	}

	static bool typeMatches(const json::Value& v, const std::string& t)
	{
		if (t == "string") return v.isString();
		if (t == "integer") return v.isInt();
		if (t == "number") return v.isNumber();
		if (t == "boolean") return v.isBool();
		if (t == "object") return v.isObject();
		if (t == "array") return v.isArray();
		if (t == "null") return v.isNull();
		return false;
	}

	void validateNode(const json::Value& v, const json::Value& schemaIn, const std::string& path,
		std::vector<std::string>& errors, int depth) const
	{
		if (depth > 64)
		{
			errors.push_back(path + ": schema too deep");
			return;
		}
		const json::Value& s = resolve(schemaIn);
		if (s.has("anyOf"))
		{
			for (const json::Value& alt : s["anyOf"].items())
			{
				std::vector<std::string> trial;
				validateNode(v, alt, path, trial, depth + 1);
				if (trial.empty())
				{
					return;
				}
			}
			errors.push_back(path + ": matches no anyOf alternative");
			return;
		}
		if (s.has("type") && !typeMatches(v, s["type"].asString()))
		{
			errors.push_back(path + ": expected " + s["type"].asString());
			return;
		}
		if (s.has("const") && !(v == s["const"]))
		{
			errors.push_back(path + ": const mismatch");
		}
		if (s.has("enum"))
		{
			bool found = false;
			for (const json::Value& e : s["enum"].items())
			{
				found = found || (e == v);
			}
			if (!found)
			{
				errors.push_back(path + ": not in enum");
			}
		}
		if (v.isString())
		{
			if (s.has("maxLength") && static_cast<int64_t>(v.asString().size()) > s["maxLength"].asInt())
			{
				errors.push_back(path + ": too long");
			}
			if (s.has("minLength") && static_cast<int64_t>(v.asString().size()) < s["minLength"].asInt())
			{
				errors.push_back(path + ": too short");
			}
			if (s.has("pattern"))
			{
				bool known = false;
				const bool ok = MatchKnownPattern(s["pattern"].asString(), v.asString(), known);
				if (!known)
				{
					errors.push_back(path + ": unknown pattern " + s["pattern"].asString());
				}
				else if (!ok)
				{
					errors.push_back(path + ": pattern mismatch");
				}
			}
		}
		if (v.isNumber() && s.has("minimum") && v.asDouble() < s["minimum"].asDouble())
		{
			errors.push_back(path + ": below minimum");
		}
		if (v.isArray() && s.has("items"))
		{
			int i = 0;
			for (const json::Value& item : v.items())
			{
				validateNode(item, s["items"], path + "[" + std::to_string(i++) + "]", errors, depth + 1);
			}
		}
		if (v.isObject())
		{
			if (s.has("maxProperties") && static_cast<int64_t>(v.size()) > s["maxProperties"].asInt())
			{
				errors.push_back(path + ": too many properties");
			}
			for (const json::Value& req : s["required"].items())
			{
				if (!v.has(req.asString()))
				{
					errors.push_back(path + ": missing required " + req.asString());
				}
			}
			const json::Value& props = s["properties"];
			const json::Value* additional = s.find("additionalProperties");
			for (const json::Value::Member& m : v.members())
			{
				if (const json::Value* ps = props.find(m.first))
				{
					validateNode(m.second, *ps, path + "." + m.first, errors, depth + 1);
				}
				else if (additional && additional->isBool() && !additional->asBool())
				{
					errors.push_back(path + ": unexpected field " + m.first);
				}
				else if (additional && additional->isObject())
				{
					validateNode(m.second, *additional, path + "." + m.first, errors, depth + 1);
				}
			}
		}
	}
};

}  // namespace odyssey::tests
