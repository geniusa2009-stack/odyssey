// Shared odyssey.game.v1 client test cases.
//
// The SAME test bodies run in two places:
//   * Tools/ProtocolCore/run_tests.cpp — native clang++ build with Unreal-like flags
//     (-fno-exceptions -fno-rtti -Wshadow -Werror), runs in CI without Unreal;
//   * OdysseyAPIAutomationTests.cpp — Unreal automation tests (Session Frontend / -ExecCmds),
//     UNREAL_EDITOR_VERIFICATION_REQUIRED.
// Every fixture is the backend's real recorded output (Tests/Fixtures/odyssey.game.v1, vendored
// with PROVENANCE.json). No JSON shape here is invented except deliberate mutations of fixtures
// (wrong protocol, older versions) that the tests name explicitly.
#pragma once

#include "OdysseyProtocol/Analysis.h"
#include "OdysseyProtocol/Command.h"
#include "OdysseyProtocol/EventSequencer.h"
#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"
#include "OdysseyProtocol/SemanticRegistry.h"
#include "OdysseyProtocol/SessionMachine.h"
#include "OdysseyProtocol/StateMirror.h"
#include "Tests/SchemaCheck.h"

#include <array>
#include <set>
#include <cstdint>
#include <string>
#include <vector>

namespace odyssey::tests
{

class Context
{
public:
	virtual ~Context() = default;
	virtual void Check(bool ok, const char* expr, const char* file, int line) = 0;
	// Path relative to the project root, e.g. "Tests/Fixtures/odyssey.game.v1/examples/x.json".
	virtual bool ReadFile(const std::string& relativePath, std::string& out) = 0;
};

#define OD_CHECK(ctx, cond) (ctx).Check(static_cast<bool>(cond), #cond, __FILE__, __LINE__)

inline const char* kExamples = "Tests/Fixtures/odyssey.game.v1/examples/";

inline json::Value Fixture(Context& ctx, const std::string& name)
{
	std::string text;
	const bool read = ctx.ReadFile(std::string(kExamples) + name + ".json", text);
	OD_CHECK(ctx, read);
	json::ParseResult r = json::parse(text);
	OD_CHECK(ctx, r.ok);
	return r.value;
}

inline json::Value File(Context& ctx, const std::string& path)
{
	std::string text;
	const bool read = ctx.ReadFile(path, text);
	OD_CHECK(ctx, read);
	json::ParseResult r = json::parse(text);
	OD_CHECK(ctx, r.ok);
	return r.value;
}

// Deterministic UUID source for tests (counter bytes → RFC 4122 v4 string).
struct CounterIds
{
	uint64_t n = 0;
	std::string operator()()
	{
		++n;
		std::array<uint8_t, 16> b{};
		for (int i = 0; i < 8; ++i)
		{
			b[15 - i] = static_cast<uint8_t>((n >> (8 * i)) & 0xFF);
			b[i] = static_cast<uint8_t>(0xA0 + i);
		}
		return FormatUuidV4(b);
	}
};

inline const HttpEffect* FindHttp(const Effects& fx, const std::string& tag)
{
	for (const HttpEffect& h : fx.http)
	{
		if (h.tag == tag)
		{
			return &h;
		}
	}
	return nullptr;
}

inline bool HasNotice(const Effects& fx, NoticeKind k, const std::string& detail = std::string())
{
	for (const Notice& n : fx.notices)
	{
		if (n.kind == k && (detail.empty() || n.detail == detail))
		{
			return true;
		}
	}
	return false;
}

inline bool HasTimer(const Effects& fx, const std::string& tag)
{
	for (const TimerEffect& t : fx.timers)
	{
		if (t.tag == tag)
		{
			return true;
		}
	}
	return false;
}

inline HttpResult Ok(int status, const json::Value& body, bool replayed = false)
{
	HttpResult r;
	r.status = status;
	r.body = json::write(body);
	r.replayedHeader = replayed;
	return r;
}

inline HttpResult TransportFailure()
{
	HttpResult r;
	r.transportFailed = true;
	return r;
}

// Drives a machine through startup with the recorded fixtures: ready → features → create →
// realtime connect → RESUMED. Leaves it Ready on the Earth Command bootstrap snapshot.
inline void StartFromFixtures(Context& ctx, SessionMachine& m)
{
	Effects fx = m.Start(Credentials());
	OD_CHECK(ctx, FindHttp(fx, "ready") != nullptr);
	fx = m.OnHttpResponse("ready", Ok(200, json::parse("{\"status\":\"ready\"}").value));
	OD_CHECK(ctx, FindHttp(fx, "features") != nullptr);
	fx = m.OnHttpResponse("features", Ok(200, Fixture(ctx, "features")));
	const HttpEffect* create = FindHttp(fx, "create");
	OD_CHECK(ctx, create != nullptr);
	fx = m.OnHttpResponse("create", Ok(201, Fixture(ctx, "create_session_response")));
	OD_CHECK(ctx, fx.persistCredentials);
	OD_CHECK(ctx, fx.wsConnect.size() == 1);
	fx = m.OnWsOpened();
	json::Value resumed = Fixture(ctx, "ws_resumed");
	resumed.set("replayed", json::Value::Int(0));
	fx = m.OnWsText(json::write(resumed));
	OD_CHECK(ctx, m.state() == SessionState::Ready);
}

// ======================================================================= test cases
inline void TestJsonRoundTripOfEveryFixture(Context& ctx)
{
	const char* names[] = {"bootstrap", "snapshot_incident", "command_request", "command_response",
		"error_stale_state", "event_incident_started", "event_inventory_changed", "event_mission_updated",
		"event_certification_granted", "future_lens_response", "black_box_response", "restore_response",
		"ws_resumed", "ws_resync_required", "features", "create_session_response", "error_mars_locked"};
	for (const char* n : names)
	{
		const json::Value v = Fixture(ctx, n);
		json::ParseResult again = json::parse(json::write(v));
		OD_CHECK(ctx, again.ok);
		OD_CHECK(ctx, again.value == v);
	}
	OD_CHECK(ctx, !json::parse("{\"a\":}").ok);
	OD_CHECK(ctx, !json::parse("[1,2").ok);
	OD_CHECK(ctx, json::parse("\"\\u00e9\\ud83d\\ude80\"").value.asString() == "\xC3\xA9\xF0\x9F\x9A\x80");
	OD_CHECK(ctx, json::parse("12345678901234").value.asInt() == 12345678901234LL);
}

inline void TestProtocolGuard(Context& ctx)
{
	json::Value boot = Fixture(ctx, "bootstrap");
	OD_CHECK(ctx, CheckProtocol(boot).ok);
	OD_CHECK(ctx, CheckFeatures(Fixture(ctx, "features")).ok);
	json::Value wrong = boot;
	wrong.set("protocol", json::Value::String("odyssey.game.v2"));
	const ProtocolCheck pc = CheckProtocol(wrong);
	OD_CHECK(ctx, !pc.ok);
	OD_CHECK(ctx, pc.reason == "protocol_mismatch:odyssey.game.v2");
	json::Value noProto = boot;
	noProto.erase("protocol");
	OD_CHECK(ctx, CheckProtocol(noProto).reason == "protocol_missing");
	// a server lacking a slice action is incompatible
	json::Value features = Fixture(ctx, "features");
	json::Value actions = json::Value::Array();
	for (const json::Value& a : features["actions"].items())
	{
		if (a["type"].asString() != "repair.perform")
		{
			actions.push(a);
		}
	}
	features.set("actions", actions);
	OD_CHECK(ctx, CheckFeatures(features).reason == "missing_action:repair.perform");
}

inline void TestBackendProtocolMismatchFailsStartup(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	m.Start(Credentials());
	m.OnHttpResponse("ready", Ok(200, json::Value::Object()));
	json::Value features = Fixture(ctx, "features");
	features.set("protocol", json::Value::String("odyssey.game.v2"));
	Effects fx = m.OnHttpResponse("features", Ok(200, features));
	OD_CHECK(ctx, m.state() == SessionState::Failed);
	OD_CHECK(ctx, HasNotice(fx, NoticeKind::ProtocolMismatch));
	OD_CHECK(ctx, fx.http.empty());  // nothing else is sent to an incompatible server
}

inline void TestUuidV4(Context& ctx)
{
	std::array<uint8_t, 16> zero{};
	OD_CHECK(ctx, FormatUuidV4(zero) == "00000000-0000-4000-8000-000000000000");
	CounterIds ids;
	const std::string a = ids();
	const std::string b = ids();
	OD_CHECK(ctx, IsUuidV4(a) && IsUuidV4(b) && a != b);
	OD_CHECK(ctx, IsValidId(a, 8, 128));
	OD_CHECK(ctx, !IsUuidV4("not-a-uuid"));
}

inline void TestCommandSerializationMatchesTheContract(Context& ctx)
{
	// The recorded request (fixture) has no defaults; ours sends protocol and actor explicitly.
	const json::Value recorded = Fixture(ctx, "command_request");
	SemanticIntent in;
	in.action = "world.zone_entered";
	in.target = "earth.command.engineering";
	CommandIds ids{recorded["command_id"].asString(), recorded["idempotency_key"].asString()};
	CommandContext c;
	c.sessionId = recorded["session_id"].asString();
	c.expectedStateVersion = recorded["expected_state_version"].asInt();
	json::Value body = BuildCommandBody(in, ids, c);
	OD_CHECK(ctx, body["protocol"].asString() == kProtocol);
	OD_CHECK(ctx, body["actor"].asString() == kCommander);
	json::Value comparable = body;
	comparable.erase("protocol");
	comparable.erase("actor");
	OD_CHECK(ctx, comparable == recorded);
	// optional fields appear only when set; params keep their JSON types
	in.anchor = "Anchor_Engineering";
	in.params.emplace_back("mode", ParamValue::Str("off"));
	in.params.emplace_back("quantity", ParamValue::Int(2));
	c.timelineId = "gt_aaaaaaaaaaaaaaaaaaaaaaaaaq";
	body = BuildCommandBody(in, ids, c);
	OD_CHECK(ctx, body["anchor"].asString() == "Anchor_Engineering");
	OD_CHECK(ctx, body["timeline_id"].asString() == "gt_aaaaaaaaaaaaaaaaaaaaaaaaaq");
	OD_CHECK(ctx, body["params"]["mode"].asString() == "off");
	OD_CHECK(ctx, body["params"]["quantity"].isInt());
	OD_CHECK(ctx, !body.has("client_timestamp"));
}

inline void TestClosedSchemaCompatibility(Context& ctx)
{
	const json::Value openapi = File(ctx, "Tests/Fixtures/odyssey.game.v1/openapi-game-v1.json");
	SchemaValidator v(openapi);
	CounterIds gen;
	SemanticIntent in;
	in.action = "cargo.transfer";
	in.target = "earth.command.hangar.luna01.cargo_hold";
	in.anchor = "Anchor_Hangar";
	in.params = {{"item", ParamValue::Str("cargo.water_tank")}, {"quantity", ParamValue::Int(1)},
		{"from", ParamValue::Str("earth.command.hangar.storage")}};
	CommandContext c;
	c.sessionId = "gs_aaaaaaaaaaaaaaaaaaaaaaaaam";
	c.timelineId = "gt_aaaaaaaaaaaaaaaaaaaaaaaaaq";
	c.expectedStateVersion = 7;
	c.clientTimestamp = "2026-10-30T10:00:00Z";
	std::vector<std::string> errors;
	OD_CHECK(ctx, v.Validate(BuildCommandBody(in, {gen(), gen()}, c), "GameCommandRequest", errors));
	OD_CHECK(ctx, errors.empty());
	// the validator really enforces the closed schema
	json::Value bad = BuildCommandBody(in, {gen(), gen()}, c);
	bad.set("position", json::Value::Array());
	errors.clear();
	OD_CHECK(ctx, !v.Validate(bad, "GameCommandRequest", errors));
	// every other request body the client sends
	json::Value restore = json::Value::Object();
	restore.set("protocol", json::Value::String(kProtocol));
	restore.set("last_seq", json::Value::Int(12));
	errors.clear();
	OD_CHECK(ctx, v.Validate(restore, "RestoreRequest", errors));
	json::Value create = json::Value::Object();
	create.set("protocol", json::Value::String(kProtocol));
	create.set("display_name", json::Value::String("Commander"));
	errors.clear();
	OD_CHECK(ctx, v.Validate(create, "CreateGameSessionRequest", errors));
	// recorded responses validate against their response schemas
	const std::pair<const char*, const char*> responses[] = {{"bootstrap", "GameBootstrap"},
		{"snapshot_incident", "GameSnapshot"}, {"command_response", "CommandResult"},
		{"error_stale_state", "GameErrorResponse"}, {"event_incident_started", "GameEventEnvelope"},
		{"future_lens_response", "GameFutureLensView"}, {"black_box_response", "GameBlackBoxView"},
		{"restore_response", "RestoreResult"}, {"create_session_response", "CreateGameSessionResponse"},
		{"features", "ServerFeatures"}, {"error_mars_locked", "GameErrorResponse"}};
	for (const auto& r : responses)
	{
		errors.clear();
		const bool ok = v.Validate(Fixture(ctx, r.first), r.second, errors);
		OD_CHECK(ctx, ok);
	}
	// WebSocket frames are not part of OpenAPI; their schema is exported from the backend models
	// (Tools/Contract/export_realtime_schema.py) into the same components/schemas layout.
	const json::Value realtime = File(ctx, "Tests/Schemas/odyssey.game.v1/realtime-frames.schema.json");
	SchemaValidator rt(realtime);
	const std::pair<const char*, const char*> frames[] = {{"ws_resumed", "GameControlFrame"},
		{"ws_resync_required", "GameControlFrame"}, {"event_incident_started", "GameEventEnvelope"},
		{"event_mission_transitioned", "GameEventEnvelope"}};
	for (const auto& f : frames)
	{
		errors.clear();
		const bool ok = rt.Validate(Fixture(ctx, f.first), f.second, errors);
		OD_CHECK(ctx, ok);
	}
	OD_CHECK(ctx, rt.HasProperty("GameControlFrame", "replayed"));
	OD_CHECK(ctx, rt.HasProperty("GameControlFrame", "restore_path"));
	// the client's ping frame is not a server frame; the backend reads only its "type"
	// the client reads only fields the contract declares
	const std::pair<const char*, const char*> reads[] = {{"GameSnapshot", "session"}, {"GameSnapshot", "timeline"},
		{"GameSnapshot", "state_version"}, {"GameSnapshot", "world"}, {"GameSnapshot", "mission"},
		{"GameSnapshot", "clock"}, {"GameSnapshot", "campaign"}, {"GameSnapshot", "resume"},
		{"SessionRef", "last_seq"}, {"ObjectView", "interactions"}, {"ObjectView", "power"},
		{"ObjectView", "infrastructure_state"}, {"InteractionView", "available"}, {"InteractionView", "reason"},
		{"ContainerView", "items"}, {"ContainerView", "mass_limit_kg"}, {"IncidentView", "stage"},
		{"MissionView", "authorization"}, {"AuthorizationView", "requirements"}, {"ClockView", "ticks_per_second"},
		{"CrewView", "intent"}, {"CueView", "line"}, {"CommandResult", "events"}, {"CommandResult", "result"},
		{"GameEventEnvelope", "seq"}, {"GameEventEnvelope", "prev_state_version"}, {"RestoreResult", "while_disconnected"},
		{"EventPage", "has_more"}, {"EventPage", "resync_required"},
		{"LensBranch", "world_hints"}, {"CausalNode", "decision"}, {"SyncResult", "events"}};
	for (const auto& r : reads)
	{
		const bool declared = v.HasProperty(r.first, r.second);
		OD_CHECK(ctx, declared);
	}
}

inline void TestIntentValidation(Context& ctx)
{
	SemanticIntent in;
	in.action = "player.Jump";
	OD_CHECK(ctx, !ValidateIntent(in).ok);
	in.action = "system.inspect";
	in.target = "earth command";  // space is not allowed in a semantic id
	OD_CHECK(ctx, ValidateIntent(in).reason == "invalid_target");
	in.target = "earth.command.engineering.power_bus_b";
	OD_CHECK(ctx, ValidateIntent(in).ok);
	for (int i = 0; i < 9; ++i)
	{
		in.params.emplace_back("p" + std::to_string(i), ParamValue::Int(i));
	}
	OD_CHECK(ctx, ValidateIntent(in).reason == "too_many_params");
}

inline void TestStateVersionHandling(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	StartFromFixtures(ctx, m);
	OD_CHECK(ctx, m.model().stateVersion == 1);
	Effects fx;
	SemanticIntent in;
	in.action = "world.zone_entered";
	in.target = "earth.command.engineering";
	const uint64_t id = m.Submit(in, fx);
	const HttpEffect* cmd = FindHttp(fx, "command");
	OD_CHECK(ctx, cmd != nullptr);
	if (!cmd)
	{
		return;
	}
	OD_CHECK(ctx, json::parse(cmd->body).value["expected_state_version"].asInt() == 1);
	// the recorded response to exactly this command: version 1 → 2, two events
	fx = m.OnHttpResponse("command", Ok(200, Fixture(ctx, "command_response")));
	OD_CHECK(ctx, m.model().stateVersion == 2);
	OD_CHECK(ctx, m.sequencer().cursor() == 2);
	OD_CHECK(ctx, HasNotice(fx, NoticeKind::CommandResolved, "applied"));
	OD_CHECK(ctx, id != 0);
	// the recorded events do not carry the new player location: the client refreshes, never guesses
	OD_CHECK(ctx, m.model().playerLocation == "earth.command.observation_deck");
	OD_CHECK(ctx, FindHttp(fx, "snapshot") != nullptr);
	// an older event never lowers the authoritative version
	json::Value old = Fixture(ctx, "command_response")["events"].items()[0];
	old.set("seq", json::Value::Int(3));
	old.set("state_version", json::Value::Int(1));
	m.OnWsText(json::write(old));
	OD_CHECK(ctx, m.model().stateVersion == 2);
	// the next command is based on the new version
	fx = Effects();
	m.Submit(in, fx);
	cmd = FindHttp(fx, "command");
	OD_CHECK(ctx, cmd && json::parse(cmd->body).value["expected_state_version"].asInt() == 2);
}

inline void TestIdempotencyRetryKeepsTheKey(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	StartFromFixtures(ctx, m);
	Effects fx;
	SemanticIntent in;
	in.action = "world.zone_entered";
	in.target = "earth.command.engineering";
	m.Submit(in, fx);
	const HttpEffect* first = FindHttp(fx, "command");
	OD_CHECK(ctx, first != nullptr);
	if (!first)
	{
		return;
	}
	const std::string body = first->body;
	const std::string key = json::parse(body).value["idempotency_key"].asString();
	OD_CHECK(ctx, first->headers.size() == 1 && first->headers[0].second == key);
	// timeout after sending: the server may have applied it → resend the identical bytes
	fx = m.OnHttpResponse("command", TransportFailure());
	OD_CHECK(ctx, HasTimer(fx, "command_retry"));
	OD_CHECK(ctx, m.ledger().busy());
	fx = m.OnTimer("command_retry");
	const HttpEffect* retry = FindHttp(fx, "command");
	OD_CHECK(ctx, retry && retry->body == body);
	// 5xx and 429 are retried with the same key too
	fx = m.OnHttpResponse("command", Ok(503, json::Value::Object()));
	fx = m.OnTimer("command_retry");
	retry = FindHttp(fx, "command");
	OD_CHECK(ctx, retry && retry->body == body);
	// a new intent queues while the first is unresolved: no new key yet
	Effects queued;
	m.Submit(in, queued);
	OD_CHECK(ctx, FindHttp(queued, "command") == nullptr);
	OD_CHECK(ctx, m.queuedIntents() == 1);
	// the replayed answer resolves it once
	fx = m.OnHttpResponse("command", Ok(200, Fixture(ctx, "command_response"), true));
	OD_CHECK(ctx, HasNotice(fx, NoticeKind::CommandResolved, "applied"));
	const HttpEffect* next = FindHttp(fx, "command");
	OD_CHECK(ctx, next != nullptr);
	if (next)
	{
		const json::Value nb = json::parse(next->body).value;
		OD_CHECK(ctx, nb["idempotency_key"].asString() != key);
		OD_CHECK(ctx, nb["command_id"].asString() != json::parse(body).value["command_id"].asString());
	}
}

inline void TestEventOrderingAndDuplicates(Context& ctx)
{
	const json::Value base = Fixture(ctx, "event_incident_started");
	const std::string sid = base["session_id"].asString();
	auto withSeq = [&](int64_t s) {
		json::Value e = base;
		e.set("seq", json::Value::Int(s));
		return e;
	};
	EventSequencer seq;
	seq.Reset(4);
	SequencerResult r = seq.Push(withSeq(7), sid);
	OD_CHECK(ctx, r.ready.empty() && r.held);
	r = seq.Push(withSeq(6), sid);
	OD_CHECK(ctx, r.ready.empty() && r.held);
	r = seq.Push(withSeq(5), sid);
	OD_CHECK(ctx, r.ready.size() == 3);
	OD_CHECK(ctx, r.ready.size() == 3 && r.ready[0]["seq"].asInt() == 5 && r.ready[2]["seq"].asInt() == 7);
	OD_CHECK(ctx, seq.cursor() == 7 && !r.held);
	r = seq.Push(withSeq(6), sid);  // duplicate (already applied)
	OD_CHECK(ctx, r.duplicates == 1 && r.ready.empty());
	r = seq.Push(withSeq(9), sid);
	r = seq.Push(withSeq(9), sid);  // duplicate (held)
	OD_CHECK(ctx, r.duplicates == 1);
	OD_CHECK(ctx, seq.duplicatesDropped() == 2);
	// envelopes from another session or protocol are rejected
	json::Value foreign = withSeq(8);
	foreign.set("session_id", json::Value::String("gs_bbbbbbbbbbbbbbbbbbbbbbbbbb"));
	OD_CHECK(ctx, seq.Push(foreign, sid).rejected == EnvelopeProblem::WrongSession);
	json::Value v2 = withSeq(8);
	v2.set("protocol", json::Value::String("odyssey.game.v2"));
	OD_CHECK(ctx, seq.Push(v2, sid).rejected == EnvelopeProblem::ProtocolMismatch);
	// a gap that never fills beyond the bound requires a restore
	EventSequencer small(2);
	small.Reset(0);
	small.Push(withSeq(3), sid);
	small.Push(withSeq(4), sid);
	OD_CHECK(ctx, small.Push(withSeq(5), sid).needsRestore);
}

inline void TestMachineHandlesDuplicateAndOutOfOrderFrames(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	StartFromFixtures(ctx, m);
	const json::Value resp = Fixture(ctx, "command_response");
	const json::Value e1 = resp["events"].items()[0];
	const json::Value e2 = resp["events"].items()[1];
	Effects fx = m.OnWsText(json::write(e2));  // out of order
	OD_CHECK(ctx, HasTimer(fx, "gap"));
	OD_CHECK(ctx, m.sequencer().cursor() == 0);
	fx = m.OnWsText(json::write(e1));
	OD_CHECK(ctx, m.sequencer().cursor() == 2);
	fx = m.OnWsText(json::write(e1));  // duplicate
	OD_CHECK(ctx, m.sequencer().cursor() == 2);
	int applied = 0;
	for (const Notice& n : fx.notices)
	{
		applied += n.kind == NoticeKind::EventApplied ? 1 : 0;
	}
	OD_CHECK(ctx, applied == 0);
	// a persistent gap is fetched over REST after the wait
	json::Value e5 = e1;
	e5.set("seq", json::Value::Int(5));
	m.OnWsText(json::write(e5));
	fx = m.OnTimer("gap");
	const HttpEffect* page = FindHttp(fx, "events");
	OD_CHECK(ctx, page && page->path.find("after_seq=2") != std::string::npos);
}

inline void TestResumeCursor(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	StartFromFixtures(ctx, m);
	m.OnHttpResponse("command", Ok(200, Fixture(ctx, "command_response")));  // stray answer: ignored
	const json::Value resp = Fixture(ctx, "command_response");
	for (const json::Value& e : resp["events"].items())
	{
		m.OnWsText(json::write(e));
	}
	OD_CHECK(ctx, m.sequencer().cursor() == 2);
	OD_CHECK(ctx, m.credentials().lastSeq == 2);
	// the socket drops → HTTP restore with the cursor, then reconnect from the restored cursor
	Effects fx = m.OnWsClosed(1006);
	OD_CHECK(ctx, m.state() == SessionState::Recovering);
	const HttpEffect* restore = FindHttp(fx, "restore");
	OD_CHECK(ctx, restore && json::parse(restore->body).value["last_seq"].asInt() == 2);
	fx = m.OnHttpResponse("restore", Ok(200, Fixture(ctx, "restore_response")));
	OD_CHECK(ctx, fx.wsConnect.size() == 1 && fx.wsConnect[0].path.find("last_seq=69") != std::string::npos);
	OD_CHECK(ctx, m.reconnectAttempts() == 1);
}

inline void TestStaleStateReconciliation(Context& ctx)
{
	// still offered after the refresh → re-submitted once with NEW ids and the new version
	{
		SessionMachine m{ClientConfig(), CounterIds()};
		StartFromFixtures(ctx, m);
		Effects fx;
		SemanticIntent in;
		in.action = "world.zone_entered";
		in.target = "earth.command.engineering";
		m.Submit(in, fx);
		const std::string firstKey = json::parse(FindHttp(fx, "command")->body).value["idempotency_key"].asString();
		fx = m.OnHttpResponse("command", Ok(409, Fixture(ctx, "error_stale_state")));
		OD_CHECK(ctx, HasNotice(fx, NoticeKind::CommandResolved, "stale"));
		OD_CHECK(ctx, FindHttp(fx, "snapshot") != nullptr);
		OD_CHECK(ctx, FindHttp(fx, "command") == nullptr);  // never retried blindly
		json::Value snap = Fixture(ctx, "create_session_response")["bootstrap"]["snapshot"];
		snap.set("state_version", json::Value::Int(2));
		fx = m.OnHttpResponse("snapshot", Ok(200, snap));
		const HttpEffect* again = FindHttp(fx, "command");
		OD_CHECK(ctx, again != nullptr);
		if (again)
		{
			const json::Value b = json::parse(again->body).value;
			OD_CHECK(ctx, b["expected_state_version"].asInt() == 2);
			OD_CHECK(ctx, b["idempotency_key"].asString() != firstKey);
		}
		// a second stale answer for the same intent is not re-submitted again
		fx = m.OnHttpResponse("command", Ok(409, Fixture(ctx, "error_stale_state")));
		fx = m.OnHttpResponse("snapshot", Ok(200, snap));
		OD_CHECK(ctx, HasNotice(fx, NoticeKind::CommandSuperseded));
		OD_CHECK(ctx, FindHttp(fx, "command") == nullptr);
	}
	// no longer offered after the refresh → superseded, nothing re-sent
	{
		SessionMachine m{ClientConfig(), CounterIds()};
		StartFromFixtures(ctx, m);
		Effects fx;
		SemanticIntent in;
		in.action = "repair.perform";  // not available before diagnosis in the snapshot
		in.target = "earth.command.engineering.power_bus_b";
		m.Submit(in, fx);
		fx = m.OnHttpResponse("command", Ok(409, Fixture(ctx, "error_stale_state")));
		fx = m.OnHttpResponse("snapshot", Ok(200, Fixture(ctx, "snapshot_incident")));
		OD_CHECK(ctx, HasNotice(fx, NoticeKind::CommandSuperseded));
		OD_CHECK(ctx, FindHttp(fx, "command") == nullptr);
	}
	// the debug control produces a real stale command
	{
		SessionMachine m{ClientConfig(), CounterIds()};
		StartFromFixtures(ctx, m);
		m.OnHttpResponse("command", Ok(200, Fixture(ctx, "command_response")));
		const json::Value recorded = Fixture(ctx, "command_response");
		for (const json::Value& e : recorded["events"].items())
		{
			m.OnWsText(json::write(e));
		}
		m.DebugForceStaleNextCommand();
		Effects fx;
		SemanticIntent in;
		in.action = "world.zone_entered";
		in.target = "earth.command.hangar";
		m.Submit(in, fx);
		const HttpEffect* cmd = FindHttp(fx, "command");
		OD_CHECK(ctx, cmd && json::parse(cmd->body).value["expected_state_version"].asInt() == 1);
	}
}

inline void TestRestoreMapping(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	Credentials stored;
	stored.sessionId = "gs_aaaaaaaaaaaaaaaaaaaaaaaaam";
	stored.token = "gst_fixture-token-0001";
	stored.lastSeq = 66;
	m.Start(stored);
	m.OnHttpResponse("ready", Ok(200, json::Value::Object()));
	Effects fx = m.OnHttpResponse("features", Ok(200, Fixture(ctx, "features")));
	const HttpEffect* restore = FindHttp(fx, "restore");
	OD_CHECK(ctx, restore && restore->authorized);
	OD_CHECK(ctx, restore && json::parse(restore->body).value["last_seq"].asInt() == 66);
	OD_CHECK(ctx, m.authorizationHeader() == "Bearer gst_fixture-token-0001");
	fx = m.OnHttpResponse("restore", Ok(200, Fixture(ctx, "restore_response")));
	const MirrorModel& mm = m.model();
	OD_CHECK(ctx, mm.missionId == "luna_01.the_last_light");
	OD_CHECK(ctx, mm.playerLocation == "luna.asteria.habitat");
	OD_CHECK(ctx, mm.lastSeq == 69 && m.sequencer().cursor() == 69);
	OD_CHECK(ctx, mm.activePhase() == "LUNA_01");
	OD_CHECK(ctx, HasNotice(fx, NoticeKind::RestoreSummary));
	OD_CHECK(ctx, HasNotice(fx, NoticeKind::SessionReady));
	// an unusable stored session (404/403 on restore) starts a new campaign instead of failing
	SessionMachine m2{ClientConfig(), CounterIds()};
	m2.Start(stored);
	m2.OnHttpResponse("ready", Ok(200, json::Value::Object()));
	m2.OnHttpResponse("features", Ok(200, Fixture(ctx, "features")));
	json::Value notFound = json::parse(
		"{\"error\":{\"code\":\"SESSION_NOT_FOUND\",\"reason\":\"session_not_found\",\"message\":\"x\","
		"\"details\":{},\"request_id\":null,\"recoverable\":false,\"state_version\":null}}")
							   .value;
	fx = m2.OnHttpResponse("restore", Ok(404, notFound));
	OD_CHECK(ctx, HasNotice(fx, NoticeKind::SessionReplaced));
	OD_CHECK(ctx, FindHttp(fx, "create") != nullptr);
}

inline void TestResyncRequiredTriggersRestore(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	StartFromFixtures(ctx, m);
	Effects fx = m.OnWsText(json::write(Fixture(ctx, "ws_resync_required")));
	OD_CHECK(ctx, m.state() == SessionState::Recovering);
	OD_CHECK(ctx, fx.wsClose);
	OD_CHECK(ctx, FindHttp(fx, "restore") != nullptr);
	// the server is down: restore retries with backoff, never gives up silently
	fx = m.OnHttpResponse("restore", TransportFailure());
	OD_CHECK(ctx, HasTimer(fx, "retry_restore"));
	fx = m.OnTimer("retry_restore");
	OD_CHECK(ctx, FindHttp(fx, "restore") != nullptr);
	fx = m.OnHttpResponse("restore", Ok(200, Fixture(ctx, "restore_response")));
	OD_CHECK(ctx, fx.wsConnect.size() == 1);
	m.OnWsOpened();
	json::Value resumed = Fixture(ctx, "ws_resumed");
	resumed.set("replayed", json::Value::Int(0));
	m.OnWsText(json::write(resumed));
	OD_CHECK(ctx, m.state() == SessionState::Ready);
}

inline void TestMirrorAppliesRecordedEvents(Context& ctx)
{
	StateMirror mirror;
	OD_CHECK(ctx, mirror.LoadSnapshot(Fixture(ctx, "create_session_response")["bootstrap"]["snapshot"]));
	OD_CHECK(ctx, mirror.model().incidents.empty());  // hidden until it happens
	OD_CHECK(ctx, mirror.model().playerLocation == "earth.command.observation_deck");
	MirrorDelta d = mirror.ApplyEvent(Fixture(ctx, "event_incident_started"));
	OD_CHECK(ctx, d.applied);
	const IncidentInfo* inc = mirror.model().incident("earth.command.power_incident");
	OD_CHECK(ctx, inc && inc->stage == "active" && !inc->resolved);
	OD_CHECK(ctx, mirror.model().activeIncidents().size() == 1);
	d = mirror.ApplyEvent(Fixture(ctx, "event_inventory_changed"));
	const ContainerInfo* locker = mirror.model().container("earth.command.engineering.spares_locker");
	OD_CHECK(ctx, locker && locker->items.size() == 2 && locker->items[0].quantity == 1);
	d = mirror.ApplyEvent(Fixture(ctx, "event_mission_updated"));
	OD_CHECK(ctx, mirror.model().authorization.present);
	OD_CHECK(ctx, !mirror.model().authorization.requirements.empty());
	d = mirror.ApplyEvent(Fixture(ctx, "event_certification_granted"));
	OD_CHECK(ctx, mirror.model().certifications.size() == 1);
	// a transition event is never applied piecemeal: it asks for the snapshot
	d = mirror.ApplyEvent(Fixture(ctx, "event_mission_transitioned"));
	OD_CHECK(ctx, d.needsSnapshot);
	// unknown future event types are ignored (forward compatible)
	json::Value future = Fixture(ctx, "event_incident_started");
	future.set("type", json::Value::String("rover.future_feature"));
	d = mirror.ApplyEvent(future);
	OD_CHECK(ctx, d.unknownType && mirror.unknownEventsIgnored() == 1);
	// ...unless the backend flags it: payload.snapshot_required always means "fetch the snapshot"
	json::Value flagged = future;
	json::Value payload = json::Value::Object();
	payload.set("snapshot_required", json::Value::Bool(true));
	flagged.set("payload", payload);
	flagged.set("seq", json::Value::Int(future["seq"].asInt() + 1));
	d = mirror.ApplyEvent(flagged);
	OD_CHECK(ctx, d.needsSnapshot && d.snapshotReason == "rover.future_feature");
	// interaction availability is refreshed from the backend, never inferred
	json::Value ic = Fixture(ctx, "command_response")["events"].items()[1];
	d = mirror.ApplyEvent(ic);
	OD_CHECK(ctx, d.refreshObjects.size() == 6);
}

inline void TestInteractionsFromBackendAndObjectRefresh(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	StartFromFixtures(ctx, m);
	const ObjectInfo* bus = m.model().object("earth.command.engineering.power_bus_b");
	OD_CHECK(ctx, bus != nullptr);
	if (!bus)
	{
		return;
	}
	// availability and its reason are the backend's, never inferred client-side
	const InteractionInfo* repair = bus->interaction("repair.perform");
	OD_CHECK(ctx, repair && !repair->available && repair->reason == "not_at_location");
	// interactions.changed → GET /objects/{id} for each listed object → mirror updated
	Effects fx = m.OnWsText(json::write(Fixture(ctx, "command_response")["events"].items()[0]));
	fx = m.OnWsText(json::write(Fixture(ctx, "command_response")["events"].items()[1]));
	const HttpEffect* get = FindHttp(fx, "object:earth.command.engineering.power_bus_b");
	OD_CHECK(ctx, get && get->path.find("/objects/earth.command.engineering.power_bus_b") != std::string::npos);
	json::Value detail;
	const json::Value incidentSnapshot = Fixture(ctx, "snapshot_incident");
	for (const json::Value& o : incidentSnapshot["world"]["objects"].items())
	{
		if (o["id"].asString() == "earth.command.engineering.power_bus_b")
		{
			detail = o;
		}
	}
	fx = m.OnHttpResponse("object:earth.command.engineering.power_bus_b", Ok(200, detail));
	bus = m.model().object("earth.command.engineering.power_bus_b");
	OD_CHECK(ctx, bus && !bus->interactionsStale && bus->status == "damaged");
	repair = bus ? bus->interaction("repair.perform") : nullptr;
	OD_CHECK(ctx, repair && repair->reason == "fault_not_diagnosed");
	const InteractionInfo* inspect = bus ? bus->interaction("system.inspect") : nullptr;
	OD_CHECK(ctx, inspect && inspect->available);
}

inline void TestClockSyncWhileTheClockRuns(Context& ctx)
{
	SessionMachine m{ClientConfig(), CounterIds()};
	StartFromFixtures(ctx, m);
	Effects fx;
	// the recorded zone entry starts the clock (REALTIME): the client must settle it periodically
	fx = m.OnWsText(json::write(Fixture(ctx, "command_response")["events"].items()[0]));
	OD_CHECK(ctx, m.model().clock.mode == "REALTIME");
	OD_CHECK(ctx, HasTimer(fx, "clock_sync"));
	// once per simulation tick (0.2 tick/s → 5 s): stays inside the backend's default rate limit
	for (const TimerEffect& t : fx.timers)
	{
		if (t.tag == "clock_sync")
		{
			OD_CHECK(ctx, t.delaySeconds > 4.99 && t.delaySeconds < 5.01);
		}
	}
	fx = m.OnTimer("clock_sync");
	const HttpEffect* sync = FindHttp(fx, "sync");
	OD_CHECK(ctx, sync && sync->method == "POST" && sync->authorized);
	OD_CHECK(ctx, HasTimer(fx, "clock_sync"));
	// while paused for the incident no sync traffic is generated
	StateMirror paused;
	paused.LoadSnapshot(Fixture(ctx, "snapshot_incident"));
	OD_CHECK(ctx, paused.model().clock.mode == "DECISION_PAUSED");
}

inline void TestSemanticRegistry(Context& ctx)
{
	SemanticRegistry reg;
	std::string err;
	OD_CHECK(ctx, reg.Load(File(ctx, "Content/Systems/SemanticIds/DT_SemanticIds_EarthCommand.json"), &err));
	OD_CHECK(ctx, err.empty());
	const SemanticEntry* bus = reg.Find("earth.command.engineering.power_bus_b");
	OD_CHECK(ctx, bus && bus->kind == SemanticKind::Object && bus->location == "earth.command.engineering");
	OD_CHECK(ctx, bus && bus->requiredInSlice);
	OD_CHECK(ctx, reg.Find("earth.command.power_incident") == nullptr);  // hidden content is never exported
	OD_CHECK(ctx, reg.UnboundRequired().empty());
	// every id of the Earth Command bootstrap is known to this build
	StateMirror mirror;
	mirror.LoadSnapshot(Fixture(ctx, "bootstrap")["snapshot"]);
	OD_CHECK(ctx, reg.UnknownInSnapshot(mirror.model()).empty());
	// unknown ids (newer server content) are reported once and never crash
	OD_CHECK(ctx, reg.Resolve("earth.command.future_room") == nullptr);
	reg.Resolve("earth.command.future_room");
	OD_CHECK(ctx, reg.unknownIds().size() == 1);
	// the LUNA-01 world is not part of this registry: reported as unknown, presentation skips it
	StateMirror luna;
	luna.LoadSnapshot(Fixture(ctx, "restore_response")["snapshot"]);
	OD_CHECK(ctx, !reg.UnknownInSnapshot(luna.model()).empty());
	json::Value dup = json::Value::Array();
	json::Value row = json::Value::Object();
	row.set("Name", json::Value::String("a"));
	row.set("Id", json::Value::String("a"));
	row.set("Kind", json::Value::String("object"));
	dup.push(row);
	dup.push(row);
	OD_CHECK(ctx, !reg.Load(dup, &err));
}

inline void TestFutureLensAndBlackBoxIngestion(Context& ctx)
{
	const FutureLensModel lens = ParseFutureLens(Fixture(ctx, "future_lens_response"));
	OD_CHECK(ctx, lens.ok);
	OD_CHECK(ctx, lens.predictionMode == "known_only" && !lens.anticipatesUnforeseeable);
	OD_CHECK(ctx, lens.branches.size() == 4 && lens.branches[0].isBaseline);
	bool sawHint = false, sawRejection = false;
	for (const LensBranch& b : lens.branches)
	{
		sawHint = sawHint || !b.worldHints.empty();
		sawRejection = sawRejection || (!b.valid && b.rejectionReason == "not_at_location");
	}
	OD_CHECK(ctx, sawHint && sawRejection);
	const BlackBoxModel bb = ParseBlackBox(Fixture(ctx, "black_box_response"));
	OD_CHECK(ctx, bb.ok && !bb.nodes.empty() && !bb.edges.empty());
	OD_CHECK(ctx, bb.edgesResolve());
	OD_CHECK(ctx, bb.simulationStatus == "concluded");
	json::Value wrong = Fixture(ctx, "black_box_response");
	wrong.set("protocol", json::Value::String("odyssey.game.v0"));
	OD_CHECK(ctx, !ParseBlackBox(wrong).ok);
}

inline void TestBackoffBounds(Context& ctx)
{
	BackoffPolicy p;
	p.initialSeconds = 0.5;
	p.maxSeconds = 4.0;
	Backoff b(p, 42);
	double last = 0;
	for (int i = 0; i < 10; ++i)
	{
		last = b.Next();
		OD_CHECK(ctx, last >= 0.0 && last <= 4.0 * 1.2 + 1e-9);
	}
	OD_CHECK(ctx, last >= 4.0 * 0.8 - 1e-9);
	b.Reset();
	OD_CHECK(ctx, b.Next() <= 0.5 * 1.2 + 1e-9);
}

// Every request the machine can emit targets a declared OpenAPI operation, with declared query
// parameters only, and a body that validates against the operation's closed request schema.
inline bool MatchTemplate(const std::string& tmpl, const std::string& path)
{
	size_t i = 0, j = 0;
	while (i < tmpl.size() && j < path.size())
	{
		if (tmpl[i] == '{')
		{
			const size_t close = tmpl.find('}', i);
			const size_t slash = path.find('/', j);
			const size_t end = slash == std::string::npos ? path.size() : slash;
			if (close == std::string::npos || end == j)
			{
				return false;
			}
			i = close + 1;
			j = end;
			continue;
		}
		if (tmpl[i] != path[j])
		{
			return false;
		}
		++i;
		++j;
	}
	return i == tmpl.size() && j == path.size();
}

inline void CheckRequestAgainstOpenApi(Context& ctx, const json::Value& openapi, const HttpEffect& h)
{
	if (h.tag == "ready")
	{
		OD_CHECK(ctx, h.path == "/api/v1/ready" && h.method == "GET" && !h.authorized);
		return;
	}
	const std::string prefix = kApiPrefix;
	OD_CHECK(ctx, h.path.rfind(prefix, 0) == 0);
	std::string rest = h.path.substr(prefix.size());
	std::string query;
	const size_t q = rest.find('?');
	if (q != std::string::npos)
	{
		query = rest.substr(q + 1);
		rest = rest.substr(0, q);
	}
	const json::Value* op = nullptr;
	for (const json::Value::Member& m : openapi["paths"].members())
	{
		if (MatchTemplate(m.first, rest))
		{
			std::string lower = h.method == "GET" ? "get" : "post";
			op = m.second.find(lower);
		}
	}
	OD_CHECK(ctx, op != nullptr);
	if (!op)
	{
		return;
	}
	// query parameters must be declared
	size_t start = 0;
	while (!query.empty() && start < query.size())
	{
		size_t amp = query.find('&', start);
		if (amp == std::string::npos) amp = query.size();
		const std::string name = query.substr(start, query.find('=', start) - start);
		bool declared = false;
		for (const json::Value& prm : (*op)["parameters"].items())
		{
			declared = declared || (prm["in"].asString() == "query" && prm["name"].asString() == name);
		}
		OD_CHECK(ctx, declared);
		start = amp + 1;
	}
	// header parameters the operation declares are sent; bodies validate against the closed schema
	for (const json::Value& prm : (*op)["parameters"].items())
	{
		if (prm["in"].asString() == "header" && prm["required"].asBool())
		{
			bool sent = false;
			for (const auto& hd : h.headers)
			{
				sent = sent || hd.first == prm["name"].asString();
			}
			OD_CHECK(ctx, sent);
		}
	}
	const json::Value& schemaRef = (*op)["requestBody"]["content"]["application/json"]["schema"]["$ref"];
	if (h.method == "POST" && schemaRef.isString())
	{
		const std::string name = schemaRef.asString().substr(std::string("#/components/schemas/").size());
		SchemaValidator v(openapi);
		std::vector<std::string> errors;
		const bool ok = v.Validate(json::parse(h.body).value, name, errors);
		OD_CHECK(ctx, ok);
	}
	// every game operation except discovery/creation needs the session token
	const bool open = rest == "/features" || rest == "/sessions" || rest == "/catalog";
	OD_CHECK(ctx, h.authorized == !open);
}

inline void TestEveryRequestMatchesTheOpenApiDocument(Context& ctx)
{
	const json::Value openapi = File(ctx, "Tests/Fixtures/odyssey.game.v1/openapi-game-v1.json");
	std::vector<HttpEffect> seen;
	auto keep = [&](const Effects& fx) {
		for (const HttpEffect& h : fx.http) seen.push_back(h);
	};
	SessionMachine m{ClientConfig(), CounterIds()};
	keep(m.Start(Credentials()));
	keep(m.OnHttpResponse("ready", Ok(200, json::Value::Object())));
	keep(m.OnHttpResponse("features", Ok(200, Fixture(ctx, "features"))));
	keep(m.OnHttpResponse("create", Ok(201, Fixture(ctx, "create_session_response"))));
	m.OnWsOpened();
	json::Value resumed = Fixture(ctx, "ws_resumed");
	resumed.set("replayed", json::Value::Int(0));
	m.OnWsText(json::write(resumed));
	Effects fx;
	SemanticIntent in;
	in.action = "cargo.transfer";
	in.target = "earth.command.hangar.luna01.cargo_hold";
	in.params = {{"item", ParamValue::Str("cargo.water_tank")}, {"quantity", ParamValue::Int(2)},
		{"from", ParamValue::Str("earth.command.hangar.storage")}};
	m.Submit(in, fx);
	keep(fx);
	keep(m.OnHttpResponse("command", Ok(200, Fixture(ctx, "command_response"))));
	const json::Value recorded = Fixture(ctx, "command_response");
	for (const json::Value& e : recorded["events"].items())
	{
		keep(m.OnWsText(json::write(e)));
	}
	keep(m.OnTimer("clock_sync"));
	json::Value later = recorded["events"].items()[0];
	later.set("seq", json::Value::Int(9));
	keep(m.OnWsText(json::write(later)));
	keep(m.OnTimer("gap"));
	keep(m.OnTimer("resource_refresh"));
	json::Value candidates = json::Value::Array();
	json::Value c1 = json::Value::Object();
	c1.set("id", json::Value::String("inspect_first"));
	c1.set("action", json::Value::String("system.inspect"));
	c1.set("target", json::Value::String("earth.command.engineering.power_bus_b"));
	candidates.push(c1);
	keep(m.RequestFutureLens(candidates, 12));
	keep(m.RequestBlackBox("gt_aaaaaaaaaaaaaaaaaaaaaaaaaq", true));
	keep(m.OnWsClosed(1006));
	OD_CHECK(ctx, seen.size() >= 10);
	std::set<std::string> tags;
	for (const HttpEffect& h : seen)
	{
		tags.insert(h.tag.rfind("object:", 0) == 0 ? "object" : h.tag);
		CheckRequestAgainstOpenApi(ctx, openapi, h);
	}
	for (const char* t : {"ready", "features", "create", "command", "sync", "events", "object", "snapshot",
			 "future_lens", "black_box", "restore"})
	{
		const bool covered = tags.count(t) == 1;
		OD_CHECK(ctx, covered);
	}
}

struct Case
{
	const char* name;
	void (*fn)(Context&);
};

inline const std::vector<Case>& AllCases()
{
	static const std::vector<Case> cases = {
		{"JsonRoundTripOfEveryFixture", &TestJsonRoundTripOfEveryFixture},
		{"ProtocolGuard", &TestProtocolGuard},
		{"BackendProtocolMismatchFailsStartup", &TestBackendProtocolMismatchFailsStartup},
		{"UuidV4", &TestUuidV4},
		{"CommandSerializationMatchesTheContract", &TestCommandSerializationMatchesTheContract},
		{"ClosedSchemaCompatibility", &TestClosedSchemaCompatibility},
		{"IntentValidation", &TestIntentValidation},
		{"StateVersionHandling", &TestStateVersionHandling},
		{"IdempotencyRetryKeepsTheKey", &TestIdempotencyRetryKeepsTheKey},
		{"EventOrderingAndDuplicates", &TestEventOrderingAndDuplicates},
		{"MachineHandlesDuplicateAndOutOfOrderFrames", &TestMachineHandlesDuplicateAndOutOfOrderFrames},
		{"ResumeCursor", &TestResumeCursor},
		{"StaleStateReconciliation", &TestStaleStateReconciliation},
		{"RestoreMapping", &TestRestoreMapping},
		{"ResyncRequiredTriggersRestore", &TestResyncRequiredTriggersRestore},
		{"MirrorAppliesRecordedEvents", &TestMirrorAppliesRecordedEvents},
		{"InteractionsFromBackendAndObjectRefresh", &TestInteractionsFromBackendAndObjectRefresh},
		{"ClockSyncWhileTheClockRuns", &TestClockSyncWhileTheClockRuns},
		{"SemanticRegistry", &TestSemanticRegistry},
		{"FutureLensAndBlackBoxIngestion", &TestFutureLensAndBlackBoxIngestion},
		{"BackoffBounds", &TestBackoffBounds},
		{"EveryRequestMatchesTheOpenApiDocument", &TestEveryRequestMatchesTheOpenApiDocument},
	};
	return cases;
}

}  // namespace odyssey::tests
