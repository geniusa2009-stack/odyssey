#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"
#include "OdysseyProtocol/Utility.h"

#include <array>
#include <cstdint>
#include <functional>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace odyssey
{

class ParamValue
{
	using Storage = std::variant<std::string, int64_t>;

public:
	static ParamValue Str(std::string value) { return ParamValue(Storage{std::in_place_type<std::string>, std::move(value)}); }
	static ParamValue Int(int64_t value) { return ParamValue(Storage{std::in_place_type<int64_t>, value}); }

	json::Value ToJson() const
	{
		return std::visit([](const auto& value) -> json::Value {
			using T = std::decay_t<decltype(value)>;
			if constexpr (std::is_same_v<T, int64_t>) return json::Value::Int(value);
			else return json::Value::String(value);
		}, value_);
	}

private:
	explicit ParamValue(Storage value) : value_(std::move(value)) {}
	Storage value_;
};

struct SemanticIntent
{
	std::string action;
	std::string target;
	std::vector<std::pair<std::string, ParamValue>> params;
	std::string actor = kCommander;
	std::string anchor;
	bool resubmitAfterStale = true;
};

struct IntentValidation
{
	bool ok = true;
	std::string reason;
};

inline IntentValidation ValidateIntent(const SemanticIntent& intent)
{
	if (!IsValidActionType(intent.action)) return {false, "invalid_action_type"};
	if (!intent.target.empty() && !IsValidId(intent.target)) return {false, "invalid_target"};
	if (!IsValidId(intent.actor)) return {false, "invalid_actor"};
	if (!intent.anchor.empty() && !IsValidId(intent.anchor)) return {false, "invalid_anchor"};
	if (intent.params.size() > 8) return {false, "too_many_params"};

	std::set<std::string> names;
	const bool valid = detail::All(intent.params, [&](const auto& entry) {
		return !entry.first.empty() && names.insert(entry.first).second;
	});
	return valid ? IntentValidation{true, {}} : IntentValidation{false, "duplicate_or_empty_param"};
}

struct CommandIds
{
	std::string commandId;
	std::string idempotencyKey;
};

struct CommandContext
{
	std::string sessionId;
	std::string timelineId;
	int64_t expectedStateVersion = 1;
	std::string clientTimestamp;
};

inline json::Value BuildCommandBody(const SemanticIntent& intent, const CommandIds& ids, const CommandContext& context)
{
	json::Value body = json::Value::Object();
	body.set("protocol", json::Value::String(kProtocol));
	body.set("command_id", json::Value::String(ids.commandId));
	body.set("session_id", json::Value::String(context.sessionId));
	if (!context.timelineId.empty()) body.set("timeline_id", json::Value::String(context.timelineId));
	body.set("expected_state_version", json::Value::Int(context.expectedStateVersion));
	body.set("idempotency_key", json::Value::String(ids.idempotencyKey));
	body.set("action", json::Value::String(intent.action));
	body.set("actor", json::Value::String(intent.actor));
	if (!intent.target.empty()) body.set("target", json::Value::String(intent.target));

	json::Value params = json::Value::Object();
	for (const auto& [name, value] : intent.params) params.set(name, value.ToJson());
	body.set("params", std::move(params));

	if (!context.clientTimestamp.empty()) body.set("client_timestamp", json::Value::String(context.clientTimestamp));
	if (!intent.anchor.empty()) body.set("anchor", json::Value::String(intent.anchor));
	return body;
}

enum class CommandOutcomeKind : uint8_t
{
	Applied,
	NoChange,
	Stale,
	Rejected,
	MissionComplete,
	SessionInvalid,
	ClientBug,
	RetrySameKey,
};

inline const char* ToString(CommandOutcomeKind kind)
{
	static constexpr std::array<std::pair<CommandOutcomeKind, const char*>, 8> names{{
		{CommandOutcomeKind::Applied, "applied"},
		{CommandOutcomeKind::NoChange, "no_change"},
		{CommandOutcomeKind::Stale, "stale"},
		{CommandOutcomeKind::Rejected, "rejected"},
		{CommandOutcomeKind::MissionComplete, "mission_complete"},
		{CommandOutcomeKind::SessionInvalid, "session_invalid"},
		{CommandOutcomeKind::ClientBug, "client_bug"},
		{CommandOutcomeKind::RetrySameKey, "retry_same_key"},
	}};
	if (const auto* value = detail::Lookup(names, kind)) return *value;
	return "unknown";
}

struct CommandOutcome
{
	CommandOutcomeKind kind = CommandOutcomeKind::RetrySameKey;
	json::Value result;
	ApiError error;
	bool replayed = false;
	int64_t stateVersion = 0;
};

inline CommandOutcomeKind ClassifyApiError(const ApiError& error)
{
	if (error.is("STALE_STATE")) return CommandOutcomeKind::Stale;
	if (error.is("MISSION_COMPLETE")) return CommandOutcomeKind::MissionComplete;
	if (error.is("PERMISSION_DENIED") || error.is("SESSION_NOT_FOUND")) return CommandOutcomeKind::SessionInvalid;
	if (error.is("VALIDATION_ERROR") || error.is("IDEMPOTENCY_KEY_REUSED")) return CommandOutcomeKind::ClientBug;
	if (error.is("RATE_LIMITED")) return CommandOutcomeKind::RetrySameKey;
	return CommandOutcomeKind::Rejected;
}

inline CommandOutcome ClassifyCommandResponse(bool transportFailed, int status, const json::Value& body, bool replayedHeader)
{
	CommandOutcome outcome;
	if (transportFailed || status == 0 || status >= 500 || status == 429) return outcome;

	if (status == 200)
	{
		outcome.result = body;
		outcome.replayed = replayedHeader;
		outcome.stateVersion = body["state_version"].asInt();
		outcome.kind = body["result"].asString() == "no_change" ? CommandOutcomeKind::NoChange : CommandOutcomeKind::Applied;
		return outcome;
	}

	if (!ParseApiError(status, body, outcome.error))
	{
		outcome.kind = CommandOutcomeKind::ClientBug;
		return outcome;
	}
	outcome.stateVersion = outcome.error.hasStateVersion ? outcome.error.stateVersion : 0;
	outcome.kind = ClassifyApiError(outcome.error);
	return outcome;
}

struct PendingCommand
{
	uint64_t localId = 0;
	SemanticIntent intent;
	CommandIds ids;
	CommandContext ctx;
	std::string bodyText;
	int attempts = 0;
	int staleResubmits = 0;
};

class CommandLedger
{
public:
	using IdSource = std::function<std::string()>;

	explicit CommandLedger(IdSource ids) : ids_(std::move(ids)) {}

	bool busy() const noexcept { return pending_.has_value(); }
	const PendingCommand* pending() const noexcept { return pending_ ? std::addressof(*pending_) : nullptr; }

	const PendingCommand* Begin(uint64_t localId, const SemanticIntent& intent, const CommandContext& context, int staleResubmits = 0)
	{
		if (pending_) return nullptr;
		PendingCommand command;
		command.localId = localId;
		command.intent = intent;
		command.ctx = context;
		command.staleResubmits = staleResubmits;
		command.ids = {FreshId(), FreshId()};
		command.bodyText = json::write(BuildCommandBody(intent, command.ids, context));
		pending_.emplace(std::move(command));
		return std::addressof(*pending_);
	}

	const std::string& NextAttempt()
	{
		++pending_->attempts;
		return pending_->bodyText;
	}

	bool Resolve(const CommandOutcome& outcome, PendingCommand* resolved)
	{
		if (!pending_ || outcome.kind == CommandOutcomeKind::RetrySameKey) return false;
		if (resolved) *resolved = *pending_;
		pending_.reset();
		return true;
	}

	void Abandon() noexcept { pending_.reset(); }
	size_t retiredKeyCount() const noexcept { return usedIds_.size(); }

private:
	std::string FreshId()
	{
		for (int guard = 0; guard < 8; ++guard)
		{
			std::string id = ids_();
			if (IsValidId(id, 8, 128) && usedIds_.insert(id).second) return id;
		}
		return {};
	}

	IdSource ids_;
	std::set<std::string> usedIds_;
	std::optional<PendingCommand> pending_;
};

}
