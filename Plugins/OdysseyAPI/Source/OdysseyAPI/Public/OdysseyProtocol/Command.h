// ODYSSEY protocol core — semantic commands and the in-flight command ledger.
//
// A *semantic intent* (what the player meant: "repair power bus B") becomes exactly one
// GameCommandRequest with its own command_id + idempotency_key. The ledger guarantees:
//   * one command in flight at a time (the server orders commands by state version anyway);
//   * a transport failure (timeout, connection reset, 5xx, 429) retries the SAME body with the
//     SAME idempotency key until the server answers — a key is never re-generated while its
//     command is unresolved, and a resolved key is never reused for another command;
//   * every HTTP answer resolves the command into a typed outcome the session machine acts on.
#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"

#include <cstdint>
#include <functional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace odyssey
{

struct ParamValue
{
	bool isInt = false;
	int64_t i = 0;
	std::string s;

	static ParamValue Str(std::string v)
	{
		ParamValue p;
		p.s = std::move(v);
		return p;
	}
	static ParamValue Int(int64_t v)
	{
		ParamValue p;
		p.isInt = true;
		p.i = v;
		return p;
	}
	json::Value ToJson() const { return isInt ? json::Value::Int(i) : json::Value::String(s); }
};

// What the player asked for. No coordinates, no outcome — the backend decides.
struct SemanticIntent
{
	std::string action;  // registered action type, e.g. "system.inspect"
	std::string target;  // semantic id ("" = no target, e.g. mission.clock_set)
	std::vector<std::pair<std::string, ParamValue>> params;
	std::string actor = kCommander;
	std::string anchor;  // optional Unreal world anchor id (logged by the server only)
	// After STALE_STATE the client refreshes and re-submits once *if* the action is still
	// offered by the backend for the target. Set false for intents that must not be repeated.
	bool resubmitAfterStale = true;
};

struct IntentValidation
{
	bool ok = true;
	std::string reason;
};

// Shape checks mirroring the closed request schema (GameCommandRequest). Legality is NOT checked
// here — that is the backend's job.
inline IntentValidation ValidateIntent(const SemanticIntent& in)
{
	if (!IsValidActionType(in.action))
	{
		return {false, "invalid_action_type"};
	}
	if (!in.target.empty() && !IsValidId(in.target))
	{
		return {false, "invalid_target"};
	}
	if (!IsValidId(in.actor))
	{
		return {false, "invalid_actor"};
	}
	if (!in.anchor.empty() && !IsValidId(in.anchor))
	{
		return {false, "invalid_anchor"};
	}
	if (in.params.size() > 8)
	{
		return {false, "too_many_params"};
	}
	std::set<std::string> names;
	for (const auto& kv : in.params)
	{
		if (kv.first.empty() || !names.insert(kv.first).second)
		{
			return {false, "duplicate_or_empty_param"};
		}
	}
	return {true, ""};
}

struct CommandIds
{
	std::string commandId;       // UUID v4
	std::string idempotencyKey;  // UUID v4 (8..128 of [A-Za-z0-9_.:-])
};

struct CommandContext
{
	std::string sessionId;
	std::string timelineId;  // optional: "" omits the field
	int64_t expectedStateVersion = 1;
	std::string clientTimestamp;  // optional, informational
};

// The exact GameCommandRequest body (closed schema: only these fields).
inline json::Value BuildCommandBody(const SemanticIntent& in, const CommandIds& ids, const CommandContext& ctx)
{
	json::Value body = json::Value::Object();
	body.set("protocol", json::Value::String(kProtocol));
	body.set("command_id", json::Value::String(ids.commandId));
	body.set("session_id", json::Value::String(ctx.sessionId));
	if (!ctx.timelineId.empty())
	{
		body.set("timeline_id", json::Value::String(ctx.timelineId));
	}
	body.set("expected_state_version", json::Value::Int(ctx.expectedStateVersion));
	body.set("idempotency_key", json::Value::String(ids.idempotencyKey));
	body.set("action", json::Value::String(in.action));
	body.set("actor", json::Value::String(in.actor));
	if (!in.target.empty())
	{
		body.set("target", json::Value::String(in.target));
	}
	json::Value params = json::Value::Object();
	for (const auto& kv : in.params)
	{
		params.set(kv.first, kv.second.ToJson());
	}
	body.set("params", std::move(params));
	if (!ctx.clientTimestamp.empty())
	{
		body.set("client_timestamp", json::Value::String(ctx.clientTimestamp));
	}
	if (!in.anchor.empty())
	{
		body.set("anchor", json::Value::String(in.anchor));
	}
	return body;
}

// ------------------------------------------------------------------ resolution
enum class CommandOutcomeKind : uint8_t
{
	Applied,          // 200, result "applied"
	NoChange,         // 200, result "no_change"
	Stale,            // 409 STALE_STATE: refresh, then maybe re-submit with NEW ids
	Rejected,         // 409/422/404: the backend refused (safe reason); do not retry
	MissionComplete,  // 409 MISSION_COMPLETE
	SessionInvalid,   // 403 PERMISSION_DENIED / 404 SESSION_NOT_FOUND
	ClientBug,        // 422 VALIDATION_ERROR / IDEMPOTENCY_KEY_REUSED: never retry, report
	RetrySameKey,     // transport failure / 5xx / 429: resend the identical body
};

inline const char* ToString(CommandOutcomeKind k)
{
	switch (k)
	{
	case CommandOutcomeKind::Applied: return "applied";
	case CommandOutcomeKind::NoChange: return "no_change";
	case CommandOutcomeKind::Stale: return "stale";
	case CommandOutcomeKind::Rejected: return "rejected";
	case CommandOutcomeKind::MissionComplete: return "mission_complete";
	case CommandOutcomeKind::SessionInvalid: return "session_invalid";
	case CommandOutcomeKind::ClientBug: return "client_bug";
	case CommandOutcomeKind::RetrySameKey: return "retry_same_key";
	}
	return "unknown";
}

struct CommandOutcome
{
	CommandOutcomeKind kind = CommandOutcomeKind::RetrySameKey;
	json::Value result;  // CommandResult (200)
	ApiError error;      // error envelope (4xx)
	bool replayed = false;
	int64_t stateVersion = 0;  // authoritative version after the answer (when known)
};

// Classify one HTTP answer to a command. `transportFailed` covers timeouts, resets, DNS, etc.
inline CommandOutcome ClassifyCommandResponse(
	bool transportFailed, int status, const json::Value& body, bool replayedHeader)
{
	CommandOutcome out;
	if (transportFailed || status == 0 || status >= 500 || status == 429)
	{
		out.kind = CommandOutcomeKind::RetrySameKey;
		return out;
	}
	if (status == 200)
	{
		out.result = body;
		out.replayed = replayedHeader;
		out.stateVersion = body["state_version"].asInt();
		out.kind = body["result"].asString() == "no_change" ? CommandOutcomeKind::NoChange : CommandOutcomeKind::Applied;
		return out;
	}
	if (!ParseApiError(status, body, out.error))
	{
		out.kind = CommandOutcomeKind::ClientBug;  // a non-envelope 4xx is a contract violation
		return out;
	}
	out.stateVersion = out.error.hasStateVersion ? out.error.stateVersion : 0;
	const ApiError& e = out.error;
	if (e.is("STALE_STATE"))
	{
		out.kind = CommandOutcomeKind::Stale;
	}
	else if (e.is("MISSION_COMPLETE"))
	{
		out.kind = CommandOutcomeKind::MissionComplete;
	}
	else if (e.is("PERMISSION_DENIED") || e.is("SESSION_NOT_FOUND"))
	{
		out.kind = CommandOutcomeKind::SessionInvalid;
	}
	else if (e.is("VALIDATION_ERROR") || e.is("IDEMPOTENCY_KEY_REUSED"))
	{
		out.kind = CommandOutcomeKind::ClientBug;
	}
	else if (e.is("RATE_LIMITED"))
	{
		out.kind = CommandOutcomeKind::RetrySameKey;
	}
	else
	{
		out.kind = CommandOutcomeKind::Rejected;  // DECISION_UNAVAILABLE, INVALID_REQUEST, NOT_FOUND
	}
	return out;
}

// ------------------------------------------------------------------ ledger
struct PendingCommand
{
	uint64_t localId = 0;  // client-side handle for presentation
	SemanticIntent intent;
	CommandIds ids;
	CommandContext ctx;
	std::string bodyText;  // the exact bytes sent; retries resend these bytes
	int attempts = 0;
	int staleResubmits = 0;
};

class CommandLedger
{
public:
	using IdSource = std::function<std::string()>;  // returns a fresh UUID v4

	explicit CommandLedger(IdSource ids) : ids_(std::move(ids)) {}

	bool busy() const { return hasPending_; }
	const PendingCommand* pending() const { return hasPending_ ? &pending_ : nullptr; }

	// Starts a new command. Returns nullptr while another command is unresolved.
	const PendingCommand* Begin(uint64_t localId, const SemanticIntent& intent, const CommandContext& ctx, int staleResubmits = 0)
	{
		if (hasPending_)
		{
			return nullptr;
		}
		PendingCommand p;
		p.localId = localId;
		p.intent = intent;
		p.ctx = ctx;
		p.staleResubmits = staleResubmits;
		p.ids.commandId = freshId();
		p.ids.idempotencyKey = freshId();
		p.bodyText = json::write(BuildCommandBody(intent, p.ids, ctx));
		pending_ = std::move(p);
		hasPending_ = true;
		return &pending_;
	}

	// The command must be (re)sent: returns the identical body every time.
	const std::string& NextAttempt()
	{
		++pending_.attempts;
		return pending_.bodyText;
	}

	// Resolves the in-flight command unless the outcome says "retry with the same key".
	// Returns true when the command is resolved (and the ledger is free again).
	bool Resolve(const CommandOutcome& outcome, PendingCommand* resolved)
	{
		if (!hasPending_ || outcome.kind == CommandOutcomeKind::RetrySameKey)
		{
			return false;
		}
		if (resolved)
		{
			*resolved = pending_;
		}
		hasPending_ = false;
		return true;
	}

	// Drops the in-flight command without an answer (session replaced). Its keys stay retired.
	void Abandon() { hasPending_ = false; }

	size_t retiredKeyCount() const { return usedIds_.size(); }

private:
	std::string freshId()
	{
		// a generator collision would silently merge two intents: refuse to ever reuse an id
		for (int guard = 0; guard < 8; ++guard)
		{
			std::string id = ids_();
			if (IsValidId(id, 8, 128) && usedIds_.insert(id).second)
			{
				return id;
			}
		}
		return std::string();  // invalid id: the server rejects it (VALIDATION_ERROR → ClientBug)
	}

	IdSource ids_;
	std::set<std::string> usedIds_;
	PendingCommand pending_;
	bool hasPending_ = false;
};

}  // namespace odyssey
