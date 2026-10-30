// ODYSSEY protocol core — odyssey.game.v1 constants, ids, errors and protocol guard.
//
// Mirrors the frozen backend contract (backend repo: docs/UNREAL_BACKEND_CONTRACT.md,
// tests/fixtures/game/openapi-game-v1.json at backend commit 4f7be839). Nothing here encodes game
// rules; it only encodes the wire contract.
#pragma once

#include "OdysseyProtocol/Json.h"

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace odyssey
{

inline constexpr const char* kProtocol = "odyssey.game.v1";
inline constexpr const char* kApiPrefix = "/api/game/v1";
inline constexpr const char* kCommander = "commander";

// ------------------------------------------------------------------ id validation (client side)
// The backend is the authority; these checks only give early, readable feedback and keep the
// client from emitting payloads the closed request schema would reject.
inline bool IsIdChar(char c)
{
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' ||
		   c == '.' || c == ':' || c == '-';
}
// ^[A-Za-z0-9_.:\-]{min,max}$  (command ids, semantic ids: 1..128; idempotency keys: 8..128)
inline bool IsValidId(const std::string& s, size_t minLen = 1, size_t maxLen = 128)
{
	if (s.size() < minLen || s.size() > maxLen)
	{
		return false;
	}
	for (char c : s)
	{
		if (!IsIdChar(c))
		{
			return false;
		}
	}
	return true;
}
// ^[a-z_]+\.[a-z_]+$, max 48
inline bool IsValidActionType(const std::string& s)
{
	if (s.empty() || s.size() > 48)
	{
		return false;
	}
	size_t dot = s.find('.');
	if (dot == std::string::npos || dot == 0 || dot + 1 == s.size() || s.find('.', dot + 1) != std::string::npos)
	{
		return false;
	}
	for (char c : s)
	{
		if (!((c >= 'a' && c <= 'z') || c == '_' || c == '.'))
		{
			return false;
		}
	}
	return true;
}
// gs_ / gt_ + base32 (lowercase a-z, 2-7), 20..32 characters
inline bool IsValidPublicId(const std::string& s, const char* prefix)
{
	const size_t n = std::char_traits<char>::length(prefix);
	if (s.compare(0, n, prefix) != 0)
	{
		return false;
	}
	const size_t body = s.size() - n;
	if (body < 20 || body > 32)
	{
		return false;
	}
	for (size_t i = n; i < s.size(); ++i)
	{
		char c = s[i];
		if (!((c >= 'a' && c <= 'z') || (c >= '2' && c <= '7')))
		{
			return false;
		}
	}
	return true;
}

// ------------------------------------------------------------------ UUID v4
// Formats 16 random bytes as an RFC 4122 version-4 UUID (lowercase). The random source is
// injected: FGuid::NewGuid() in Unreal, a seeded generator in tests.
inline std::string FormatUuidV4(std::array<uint8_t, 16> b)
{
	b[6] = static_cast<uint8_t>((b[6] & 0x0F) | 0x40);
	b[8] = static_cast<uint8_t>((b[8] & 0x3F) | 0x80);
	static const char* hex = "0123456789abcdef";
	std::string out;
	out.reserve(36);
	for (size_t i = 0; i < 16; ++i)
	{
		if (i == 4 || i == 6 || i == 8 || i == 10)
		{
			out += '-';
		}
		out += hex[b[i] >> 4];
		out += hex[b[i] & 0x0F];
	}
	return out;
}

inline bool IsUuidV4(const std::string& s)
{
	if (s.size() != 36 || s[8] != '-' || s[13] != '-' || s[18] != '-' || s[23] != '-' || s[14] != '4')
	{
		return false;
	}
	const char variant = s[19];
	if (!(variant == '8' || variant == '9' || variant == 'a' || variant == 'b'))
	{
		return false;
	}
	for (size_t i = 0; i < s.size(); ++i)
	{
		if (i == 8 || i == 13 || i == 18 || i == 23)
		{
			continue;
		}
		char c = s[i];
		if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
		{
			return false;
		}
	}
	return true;
}

// ------------------------------------------------------------------ errors
// The shared public error envelope: {"error": {code, reason, message, details, request_id,
// recoverable, state_version}}. Codes are frozen; reasons may grow (treat unknown as the code).
struct ApiError
{
	int httpStatus = 0;
	std::string code;    // STALE_STATE, DECISION_UNAVAILABLE, ...
	std::string reason;  // not_at_location, stale_state, ...
	std::string message;
	bool recoverable = false;
	bool hasStateVersion = false;
	int64_t stateVersion = 0;
	json::Value details;
	std::string requestId;

	bool is(const char* c) const { return code == c; }
};

inline bool ParseApiError(int httpStatus, const json::Value& body, ApiError& out)
{
	const json::Value* err = body.find("error");
	if (!err || !err->isObject())
	{
		return false;
	}
	out.httpStatus = httpStatus;
	out.code = (*err)["code"].asString();
	out.reason = (*err)["reason"].stringOr(out.code);
	out.message = (*err)["message"].asString();
	out.recoverable = (*err)["recoverable"].asBool();
	out.hasStateVersion = (*err)["state_version"].isNumber();
	out.stateVersion = (*err)["state_version"].asInt();
	out.details = (*err)["details"];
	out.requestId = (*err)["request_id"].asString();
	return !out.code.empty();
}

// ------------------------------------------------------------------ protocol guard
struct ProtocolCheck
{
	bool ok = false;
	std::string reason;  // empty when ok
};

// Every top-level odyssey.game.v1 document carries "protocol". A different value means the client
// must not interpret the payload (connect to a compatible server or update the client).
inline ProtocolCheck CheckProtocol(const json::Value& doc)
{
	const json::Value* p = doc.find("protocol");
	if (!p || !p->isString())
	{
		return {false, "protocol_missing"};
	}
	if (p->asString() != kProtocol)
	{
		return {false, "protocol_mismatch:" + p->asString()};
	}
	return {true, ""};
}

// Actions the vertical slice needs; a server whose /features lacks one is incompatible.
inline std::vector<std::string> RequiredActions()
{
	return {"world.zone_entered", "system.inspect", "system.set_mode", "repair.perform",
			"power.reroute",      "mission.clock_set", "mission.authorize", "npc.context_request"};
}

inline ProtocolCheck CheckFeatures(const json::Value& features)
{
	const ProtocolCheck pc = CheckProtocol(features);
	if (!pc.ok)
	{
		return pc;
	}
	for (const std::string& required : RequiredActions())
	{
		bool found = false;
		for (const json::Value& a : features["actions"].items())
		{
			if (a["type"].asString() == required)
			{
				found = true;
				break;
			}
		}
		if (!found)
		{
			return {false, "missing_action:" + required};
		}
	}
	return {true, ""};
}

}  // namespace odyssey
