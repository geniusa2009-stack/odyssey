// ODYSSEY protocol core — the client session machine (functional core, imperative shell).
//
// All odyssey.game.v1 client behaviour lives here, engine-independent: startup (readiness →
// features → restore or create → snapshot → realtime), commands (ledger, same-key retries,
// stale-state reconciliation), realtime (sequencer → mirror → refreshes), clock settlement,
// reconnect/restore with backoff, and analysis requests. It performs NO I/O: every input method
// returns `Effects` (HTTP requests, socket actions, timers, notifications) that a shell executes.
//   * Unreal: UOdysseyBackendSubsystem executes effects with FHttpModule / IWebSocketsModule /
//     FTSTicker and turns notifications into delegates.
//   * Tests:  Tools/ProtocolCore drives it directly (fixtures) or through a POSIX shell against a
//     live backend (including a server restart).
#pragma once

#include "OdysseyProtocol/Analysis.h"
#include "OdysseyProtocol/Backoff.h"
#include "OdysseyProtocol/Command.h"
#include "OdysseyProtocol/EventSequencer.h"
#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"
#include "OdysseyProtocol/StateMirror.h"

#include <algorithm>
#include <cstdint>
#include <deque>
#include <functional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace odyssey
{

struct ClientConfig
{
	std::string apiPrefix = kApiPrefix;     // relative to the server root (base URL is the shell's)
	std::string readyPath = "/api/v1/ready";
	std::string displayName = "Commander";
	double requestTimeoutSeconds = 10.0;
	double commandTimeoutSeconds = 10.0;
	// Request budget: the backend rate-limits every client to ODYSSEY_RATE_LIMIT_PER_MINUTE
	// (default 120/min, shared by all default-bucket endpoints). Settling the clock more often
	// than once per simulation tick yields nothing, so the sync cadence follows the clock:
	// REALTIME 0.2 tick/s → every 5 s, ACCELERATED 0.8 tick/s → every 1.25 s (never < min).
	double clockSyncMinSeconds = 1.0;
	double clockSyncMaxSeconds = 5.0;
	double resourceRefreshSeconds = 5.0;      // snapshot at most this often for resource values
	double gapWaitSeconds = 1.0;              // wait for a missing seq before fetching it
	double pingIntervalSeconds = 20.0;
	size_t maxQueuedIntents = 8;
	size_t maxObjectRefreshBatch = 6;
	BackoffPolicy backoff;
};

struct Credentials
{
	std::string sessionId;
	std::string token;
	int64_t lastSeq = 0;
	bool valid() const { return !sessionId.empty() && !token.empty(); }
};

enum class SessionState : uint8_t
{
	Idle,
	CheckingReady,
	LoadingFeatures,
	Restoring,
	CreatingSession,
	ConnectingRealtime,
	Ready,
	Recovering,
	Failed,
};

inline const char* ToString(SessionState s)
{
	switch (s)
	{
	case SessionState::Idle: return "Idle";
	case SessionState::CheckingReady: return "CheckingReady";
	case SessionState::LoadingFeatures: return "LoadingFeatures";
	case SessionState::Restoring: return "Restoring";
	case SessionState::CreatingSession: return "CreatingSession";
	case SessionState::ConnectingRealtime: return "ConnectingRealtime";
	case SessionState::Ready: return "Ready";
	case SessionState::Recovering: return "Recovering";
	case SessionState::Failed: return "Failed";
	}
	return "?";
}

struct HttpEffect
{
	std::string tag;      // routes the answer back: "ready", "command", "object:<id>", ...
	std::string method;   // GET / POST
	std::string path;     // absolute path on the server, e.g. /api/game/v1/sessions/gs_x/commands
	std::string body;     // JSON text ("" for GET)
	bool authorized = false;
	double timeoutSeconds = 10.0;
	std::vector<std::pair<std::string, std::string>> headers;  // extra headers (Idempotency-Key)
};

struct WsConnectEffect
{
	std::string path;  // /api/game/v1/ws/sessions/<id>?last_seq=N (token goes in the header)
};

struct TimerEffect
{
	std::string tag;
	double delaySeconds = 0;
};

enum class NoticeKind : uint8_t
{
	StateChanged,       // detail = new SessionState
	SessionReady,       // first time the mirror is usable
	SnapshotApplied,    // detail = reason
	EventApplied,       // detail = event type, data = envelope, ids = changed semantic ids
	CommandQueued,      // localId
	CommandSent,        // localId, detail = attempt number
	CommandResolved,    // localId, detail = outcome kind, data = result or error envelope
	CommandSuperseded,  // localId: stale and no longer offered after refresh
	IntentRejected,     // localId, detail = local validation reason (nothing was sent)
	RestoreSummary,     // data = while_disconnected
	SessionReplaced,    // the stored session was unusable; a new campaign started
	SessionInvalid,     // token rejected mid-session: needs the player's decision
	ProtocolMismatch,   // fatal: detail = reason
	UnknownSemanticIds, // ids = ids this build does not know
	FutureLensReady,    // data = GameFutureLensView
	BlackBoxReady,      // data = GameBlackBoxView
	InfoEvent,          // future_lens.ready / black_box.ready / checkpoint.saved envelopes
	Error,              // detail = what failed (non-fatal)
};

struct Notice
{
	NoticeKind kind = NoticeKind::Error;
	std::string detail;
	uint64_t localId = 0;
	json::Value data;
	std::vector<std::string> ids;
};

struct Effects
{
	std::vector<HttpEffect> http;
	std::vector<WsConnectEffect> wsConnect;
	bool wsClose = false;
	std::vector<std::string> wsSend;
	std::vector<TimerEffect> timers;
	std::vector<Notice> notices;
	bool persistCredentials = false;  // the shell saves credentials() (never in source control)

	void merge(Effects&& o)
	{
		for (auto& h : o.http) http.push_back(std::move(h));
		for (auto& w : o.wsConnect) wsConnect.push_back(std::move(w));
		wsClose = wsClose || o.wsClose;
		for (auto& s : o.wsSend) wsSend.push_back(std::move(s));
		for (auto& t : o.timers) timers.push_back(std::move(t));
		for (auto& n : o.notices) notices.push_back(std::move(n));
		persistCredentials = persistCredentials || o.persistCredentials;
	}
};

struct HttpResult
{
	bool transportFailed = false;  // timeout, refused, reset, DNS — the request may or may not have run
	int status = 0;
	std::string body;
	bool replayedHeader = false;   // Idempotent-Replayed: true
};

class SessionMachine
{
public:
	using IdSource = CommandLedger::IdSource;

	SessionMachine(ClientConfig cfg, IdSource ids)
		: cfg_(std::move(cfg)), ledger_(std::move(ids)), backoff_(cfg_.backoff), cmdBackoff_(cfg_.backoff, 0xC0FFEEull)
	{
	}

	// ---------------------------------------------------------------- observers
	SessionState state() const { return state_; }
	const MirrorModel& model() const { return mirror_.model(); }
	const StateMirror& mirror() const { return mirror_; }
	const EventSequencer& sequencer() const { return seq_; }
	const CommandLedger& ledger() const { return ledger_; }
	const Credentials& credentials() const { return creds_; }
	const json::Value& features() const { return features_; }
	bool realtimeOpen() const { return wsOpen_; }
	int reconnectAttempts() const { return reconnects_; }
	size_t queuedIntents() const { return queue_.size(); }
	const std::string& lastCommandSummary() const { return lastCommand_; }
	std::string authorizationHeader() const { return creds_.token.empty() ? std::string() : "Bearer " + creds_.token; }

	// ---------------------------------------------------------------- lifecycle
	Effects Start(const Credentials& stored)
	{
		Effects fx;
		creds_ = stored;
		setState(SessionState::CheckingReady, fx);
		fx.http.push_back(get("ready", cfg_.readyPath, false));
		return fx;
	}

	// Explicit restore (debug control, or the player pressing "resync").
	Effects RequestRestore()
	{
		Effects fx;
		beginRecover(fx, "requested");
		return fx;
	}

	Effects Shutdown()
	{
		Effects fx;
		shuttingDown_ = true;
		fx.wsClose = wsOpen_ || wsConnecting_;
		wsOpen_ = wsConnecting_ = false;
		setState(SessionState::Idle, fx);
		return fx;
	}

	// ---------------------------------------------------------------- commands
	// Returns the local id of the intent (0 = rejected locally; see the IntentRejected notice).
	uint64_t Submit(const SemanticIntent& intent, Effects& fx)
	{
		const uint64_t id = ++nextLocalId_;
		const IntentValidation v = ValidateIntent(intent);
		if (!v.ok)
		{
			fx.notices.push_back(note(NoticeKind::IntentRejected, v.reason, id));
			return id;
		}
		if (queue_.size() >= cfg_.maxQueuedIntents)
		{
			fx.notices.push_back(note(NoticeKind::IntentRejected, "queue_full", id));
			return id;
		}
		queue_.push_back({id, intent, 0});
		fx.notices.push_back(note(NoticeKind::CommandQueued, intent.action, id));
		pump(fx);
		return id;
	}

	// Debug control: the next command is sent with an outdated expected_state_version.
	void DebugForceStaleNextCommand() { forceStale_ = true; }

	// ---------------------------------------------------------------- analysis
	Effects RequestFutureLens(const json::Value& candidates, int horizonTicks)
	{
		Effects fx;
		if (!creds_.valid())
		{
			return fx;
		}
		json::Value body = json::Value::Object();
		body.set("protocol", json::Value::String(kProtocol));
		body.set("candidates", candidates);
		body.set("horizon_ticks", json::Value::Int(horizonTicks));
		fx.http.push_back(post("future_lens", sessionPath("/future-lens"), body, true));
		return fx;
	}

	Effects RequestBlackBox(const std::string& timelineId, bool counterfactuals)
	{
		Effects fx;
		if (!creds_.valid())
		{
			return fx;
		}
		std::string path = sessionPath("/black-box") + "?counterfactuals=" + (counterfactuals ? "true" : "false");
		if (!timelineId.empty())
		{
			path += "&timeline_id=" + timelineId;
		}
		fx.http.push_back(get("black_box", path, true));
		return fx;
	}

	// ---------------------------------------------------------------- shell inputs
	Effects OnHttpResponse(const std::string& tag, const HttpResult& r)
	{
		Effects fx;
		json::Value body;
		bool parsed = false;
		if (!r.transportFailed && !r.body.empty())
		{
			json::ParseResult pr = json::parse(r.body);
			parsed = pr.ok;
			if (pr.ok)
			{
				body = std::move(pr.value);
			}
		}
		if (tag == "ready") onReady(r, fx);
		else if (tag == "features") onFeatures(r, body, parsed, fx);
		else if (tag == "create") onCreate(r, body, fx);
		else if (tag == "restore") onRestore(r, body, fx);
		else if (tag == "snapshot") onSnapshot(r, body, fx);
		else if (tag == "command") onCommand(r, body, fx);
		else if (tag == "sync") onSync(r, body, fx);
		else if (tag == "events") onEventsPage(r, body, fx);
		else if (tag.rfind("object:", 0) == 0) onObject(tag.substr(7), r, body, fx);
		else if (tag == "future_lens") onAnalysis(NoticeKind::FutureLensReady, r, body, fx);
		else if (tag == "black_box") onAnalysis(NoticeKind::BlackBoxReady, r, body, fx);
		return fx;
	}

	Effects OnWsOpened()
	{
		Effects fx;
		wsConnecting_ = false;
		wsOpen_ = true;
		fx.timers.push_back({"ping", cfg_.pingIntervalSeconds});
		return fx;
	}

	Effects OnWsText(const std::string& text)
	{
		Effects fx;
		json::ParseResult pr = json::parse(text);
		if (!pr.ok || !pr.value.isObject())
		{
			fx.notices.push_back(note(NoticeKind::Error, "realtime_bad_frame"));
			return fx;
		}
		const json::Value& msg = pr.value;
		if (!CheckProtocol(msg).ok)
		{
			fx.notices.push_back(note(NoticeKind::Error, "realtime_protocol_mismatch"));
			return fx;
		}
		if (IsControlFrame(msg))
		{
			onControl(msg, fx);
			return fx;
		}
		pushEvents({msg}, fx);
		return fx;
	}

	Effects OnWsClosed(int code)
	{
		Effects fx;
		const bool wasOpen = wsOpen_ || wsConnecting_;
		wsOpen_ = wsConnecting_ = false;
		if (shuttingDown_ || state_ == SessionState::Failed)
		{
			return fx;
		}
		if (code == 1008)
		{
			// policy violation: bad token/session/cursor → the HTTP restore path decides
			fx.notices.push_back(note(NoticeKind::Error, "realtime_refused"));
		}
		if (wasOpen || state_ == SessionState::Ready || state_ == SessionState::ConnectingRealtime)
		{
			beginRecover(fx, "realtime_closed");
		}
		return fx;
	}

	Effects OnTimer(const std::string& tag)
	{
		Effects fx;
		if (tag == "retry_ready")
		{
			fx.http.push_back(get("ready", cfg_.readyPath, false));
		}
		else if (tag == "retry_restore")
		{
			restoreInFlight_ = false;
			sendRestore(fx);
		}
		else if (tag == "command_retry")
		{
			resendPending(fx);
		}
		else if (tag == "clock_sync")
		{
			syncTimerArmed_ = false;
			if (state_ == SessionState::Ready && clockRunning() && !syncInFlight_ && !ledger_.busy())
			{
				syncInFlight_ = true;
				json::Value body = json::Value::Object();
				body.set("protocol", json::Value::String(kProtocol));
				fx.http.push_back(post("sync", sessionPath("/sync"), body, true));
			}
			armClockSync(fx);
		}
		else if (tag == "resource_refresh")
		{
			resourceTimerArmed_ = false;
			if (resourcesStale_)  // skip when a snapshot already landed after the last change
			{
				requestSnapshot(fx, "resources");
			}
		}
		else if (tag == "gap")
		{
			gapTimerArmed_ = false;
			if (seq_.heldCount() > 0)
			{
				fetchEvents(fx);
			}
		}
		else if (tag == "ping")
		{
			if (wsOpen_)
			{
				fx.wsSend.push_back("{\"type\":\"ping\"}");
				fx.timers.push_back({"ping", cfg_.pingIntervalSeconds});
			}
		}
		return fx;
	}

private:
	struct QueuedIntent
	{
		uint64_t localId;
		SemanticIntent intent;
		int staleResubmits;
	};

	// ---------------------------------------------------------------- helpers
	static Notice note(NoticeKind k, std::string detail = {}, uint64_t localId = 0)
	{
		Notice n;
		n.kind = k;
		n.detail = std::move(detail);
		n.localId = localId;
		return n;
	}
	void setState(SessionState s, Effects& fx)
	{
		if (state_ != s)
		{
			state_ = s;
			fx.notices.push_back(note(NoticeKind::StateChanged, ToString(s)));
		}
	}
	std::string sessionPath(const std::string& suffix) const { return cfg_.apiPrefix + "/sessions/" + creds_.sessionId + suffix; }
	HttpEffect get(const std::string& tag, const std::string& path, bool auth) const
	{
		HttpEffect h;
		h.tag = tag;
		h.method = "GET";
		h.path = path;
		h.authorized = auth;
		h.timeoutSeconds = cfg_.requestTimeoutSeconds;
		return h;
	}
	HttpEffect post(const std::string& tag, const std::string& path, const json::Value& body, bool auth) const
	{
		HttpEffect h;
		h.tag = tag;
		h.method = "POST";
		h.path = path;
		h.body = json::write(body);
		h.authorized = auth;
		h.timeoutSeconds = cfg_.requestTimeoutSeconds;
		return h;
	}
	bool clockRunning() const
	{
		const std::string& mode = mirror_.model().clock.mode;
		return mode == "REALTIME" || mode == "ACCELERATED";
	}

	// ---------------------------------------------------------------- startup
	void onReady(const HttpResult& r, Effects& fx)
	{
		if (r.transportFailed || r.status != 200)
		{
			fx.timers.push_back({"retry_ready", backoff_.Next()});
			return;
		}
		backoff_.Reset();
		setState(SessionState::LoadingFeatures, fx);
		fx.http.push_back(get("features", cfg_.apiPrefix + "/features", false));
	}

	void onFeatures(const HttpResult& r, const json::Value& body, bool parsed, Effects& fx)
	{
		if (r.transportFailed || r.status != 200 || !parsed)
		{
			fx.timers.push_back({"retry_ready", backoff_.Next()});
			setState(SessionState::CheckingReady, fx);
			return;
		}
		const ProtocolCheck pc = CheckFeatures(body);
		if (!pc.ok)
		{
			fail(fx, pc.reason);
			return;
		}
		features_ = body;
		if (creds_.valid())
		{
			setState(SessionState::Restoring, fx);
			sendRestore(fx);
		}
		else
		{
			createSession(fx);
		}
	}

	void createSession(Effects& fx)
	{
		setState(SessionState::CreatingSession, fx);
		json::Value body = json::Value::Object();
		body.set("protocol", json::Value::String(kProtocol));
		body.set("display_name", json::Value::String(cfg_.displayName));
		fx.http.push_back(post("create", cfg_.apiPrefix + "/sessions", body, false));
	}

	void onCreate(const HttpResult& r, const json::Value& body, Effects& fx)
	{
		if (r.transportFailed || r.status >= 500)
		{
			// creating is not idempotent: a lost answer leaves an orphan session (harmless); retry
			fx.timers.push_back({"retry_ready", backoff_.Next()});
			setState(SessionState::CheckingReady, fx);
			return;
		}
		if (r.status != 201 || !CheckProtocol(body).ok || !CheckProtocol(body["bootstrap"]).ok)
		{
			fail(fx, "create_session_failed");
			return;
		}
		creds_.token = body["session_token"].asString();
		creds_.sessionId = body["bootstrap"]["snapshot"]["session"]["id"].asString();
		fx.persistCredentials = true;
		if (!loadSnapshot(body["bootstrap"]["snapshot"], "bootstrap", fx))
		{
			return;
		}
		connectRealtime(fx);
	}

	// ---------------------------------------------------------------- restore / recover
	void sendRestore(Effects& fx)
	{
		if (restoreInFlight_)
		{
			return;
		}
		restoreInFlight_ = true;
		json::Value body = json::Value::Object();
		body.set("protocol", json::Value::String(kProtocol));
		body.set("last_seq", json::Value::Int(seq_.cursor() > 0 ? seq_.cursor() : creds_.lastSeq));
		fx.http.push_back(post("restore", sessionPath("/restore"), body, true));
	}

	void beginRecover(Effects& fx, const std::string& why)
	{
		if (state_ == SessionState::Failed || shuttingDown_ || !creds_.valid())
		{
			return;
		}
		if (state_ != SessionState::Recovering)
		{
			++reconnects_;
			fx.notices.push_back(note(NoticeKind::Error, "recovering:" + why));
		}
		setState(SessionState::Recovering, fx);
		if (wsOpen_ || wsConnecting_)
		{
			fx.wsClose = true;
			wsOpen_ = wsConnecting_ = false;
		}
		sendRestore(fx);
	}

	void onRestore(const HttpResult& r, const json::Value& body, Effects& fx)
	{
		restoreInFlight_ = false;
		if (r.transportFailed || r.status >= 500 || r.status == 429)
		{
			fx.timers.push_back({"retry_restore", backoff_.Next()});
			return;
		}
		if (r.status == 403 || r.status == 404)
		{
			if (state_ == SessionState::Restoring)
			{
				// stored session unusable (expired/foreign token, wiped server): start a new campaign
				fx.notices.push_back(note(NoticeKind::SessionReplaced, std::to_string(r.status)));
				creds_ = Credentials();
				createSession(fx);
			}
			else
			{
				fx.notices.push_back(note(NoticeKind::SessionInvalid, std::to_string(r.status)));
				fail(fx, "session_invalid");
			}
			return;
		}
		if (r.status != 200 || !CheckProtocol(body).ok)
		{
			fail(fx, r.status == 422 ? "content_version_mismatch_or_invalid" : "restore_failed");
			return;
		}
		backoff_.Reset();
		if (!loadSnapshot(body["snapshot"], body["resync_required"].asBool() ? "restore_resync" : "restore", fx))
		{
			return;
		}
		Notice n = note(NoticeKind::RestoreSummary, body["reason"].asString());
		n.data = body["while_disconnected"];
		fx.notices.push_back(std::move(n));
		if (!wsOpen_ && !wsConnecting_)
		{
			connectRealtime(fx);
		}
	}

	void connectRealtime(Effects& fx)
	{
		setState(SessionState::ConnectingRealtime, fx);
		wsConnecting_ = true;
		fx.wsConnect.push_back(
			{cfg_.apiPrefix + "/ws/sessions/" + creds_.sessionId + "?last_seq=" + std::to_string(seq_.cursor())});
	}

	bool loadSnapshot(const json::Value& snap, const std::string& reason, Effects& fx)
	{
		const int64_t previous = seq_.cursor();
		std::string err;
		if (!mirror_.LoadSnapshot(snap, &err))
		{
			fail(fx, err.empty() ? "snapshot_invalid" : err);
			return false;
		}
		seq_.Reset(mirror_.model().lastSeq);
		creds_.lastSeq = mirror_.model().lastSeq;
		resourcesStale_ = false;
		fx.persistCredentials = true;
		Notice n = note(NoticeKind::SnapshotApplied, reason);
		fx.notices.push_back(std::move(n));
		if (!readyOnce_ && mirror_.model().loaded)
		{
			readyOnce_ = true;
			fx.notices.push_back(note(NoticeKind::SessionReady));
		}
		if (previous > seq_.cursor())
		{
			// the snapshot predates events already applied: replay them on top of it
			fetchEvents(fx);
		}
		armClockSync(fx);
		return true;
	}

	void requestSnapshot(Effects& fx, const std::string& reason)
	{
		if (snapshotInFlight_)
		{
			snapshotAgain_ = true;
			return;
		}
		snapshotInFlight_ = true;
		snapshotReason_ = reason;
		fx.http.push_back(get("snapshot", sessionPath("/snapshot"), true));
	}

	void onSnapshot(const HttpResult& r, const json::Value& body, Effects& fx)
	{
		snapshotInFlight_ = false;
		if (r.transportFailed || r.status >= 500)
		{
			beginRecover(fx, "snapshot_failed");
			return;
		}
		if (r.status != 200)
		{
			fx.notices.push_back(note(NoticeKind::Error, "snapshot_status_" + std::to_string(r.status)));
			if (r.status == 403 || r.status == 404)
			{
				fail(fx, "session_invalid");
			}
			return;
		}
		if (!loadSnapshot(body, snapshotReason_, fx))
		{
			return;
		}
		// reconcile only on a snapshot at least as new as the version the server reported in
		// STALE_STATE (an older, already in-flight snapshot would decide on outdated state)
		if (pendingStale_ && mirror_.model().stateVersion >= staleServerVersion_)
		{
			reconcileStale(fx);
		}
		else if (pendingStale_)
		{
			snapshotAgain_ = true;
		}
		if (snapshotAgain_)
		{
			snapshotAgain_ = false;
			requestSnapshot(fx, "coalesced");
		}
		pump(fx);
	}

	void fail(Effects& fx, const std::string& reason)
	{
		fx.notices.push_back(note(reason.rfind("protocol", 0) == 0 || reason.rfind("missing_action", 0) == 0
									  ? NoticeKind::ProtocolMismatch
									  : NoticeKind::Error,
			reason));
		if (wsOpen_ || wsConnecting_)
		{
			fx.wsClose = true;
			wsOpen_ = wsConnecting_ = false;
		}
		setState(SessionState::Failed, fx);
	}

	// ---------------------------------------------------------------- realtime
	void onControl(const json::Value& msg, Effects& fx)
	{
		const std::string& t = msg["type"].asString();
		if (t == "RESUMED")
		{
			reconnectBackoffReset(fx);
		}
		else if (t == "CONNECTED")
		{
			reconnectBackoffReset(fx);
			if (msg["last_seq"].asInt() > seq_.cursor())
			{
				fetchEvents(fx);  // committed before we subscribed: fetch them over REST
			}
		}
		else if (t == "RESYNC_REQUIRED")
		{
			beginRecover(fx, msg["reason"].stringOr("resync_required"));
		}
	}

	void reconnectBackoffReset(Effects& fx)
	{
		backoff_.Reset();
		if (state_ == SessionState::ConnectingRealtime || state_ == SessionState::Recovering)
		{
			setState(SessionState::Ready, fx);
		}
		pump(fx);
	}

	void pushEvents(const std::vector<json::Value>& envs, Effects& fx)
	{
		SequencerResult sr = seq_.PushAll(envs, creds_.sessionId);
		for (const json::Value& env : sr.ready)
		{
			applyEvent(env, fx);
		}
		creds_.lastSeq = seq_.cursor();
		if (sr.needsRestore)
		{
			beginRecover(fx, "event_gap");
			return;
		}
		if (sr.held && !gapTimerArmed_)
		{
			gapTimerArmed_ = true;
			fx.timers.push_back({"gap", cfg_.gapWaitSeconds});
		}
	}

	void applyEvent(const json::Value& env, Effects& fx)
	{
		MirrorDelta d = mirror_.ApplyEvent(env);
		const std::string& t = d.type;
		if (t == "future_lens.ready" || t == "black_box.ready" || t == "checkpoint.saved")
		{
			Notice n = note(NoticeKind::InfoEvent, t);
			n.data = env;
			fx.notices.push_back(std::move(n));
		}
		else
		{
			Notice n = note(NoticeKind::EventApplied, t);
			n.data = env;
			n.ids = d.changedIds;
			fx.notices.push_back(std::move(n));
		}
		if (d.needsSnapshot)
		{
			requestSnapshot(fx, d.snapshotReason);
		}
		if (!d.refreshObjects.empty())
		{
			if (d.refreshObjects.size() > cfg_.maxObjectRefreshBatch)
			{
				requestSnapshot(fx, "many_objects");
			}
			else
			{
				for (const std::string& id : d.refreshObjects)
				{
					if (objectInFlight_.insert(id).second)
					{
						fx.http.push_back(get("object:" + id, sessionPath("/objects/" + id), true));
					}
				}
			}
		}
		resourcesStale_ = resourcesStale_ || d.resourcesStale;
		if (d.resourcesStale && !resourceTimerArmed_)
		{
			resourceTimerArmed_ = true;
			fx.timers.push_back({"resource_refresh", cfg_.resourceRefreshSeconds});
		}
		if (t == "clock.updated")
		{
			armClockSync(fx);
		}
	}

	void fetchEvents(Effects& fx)
	{
		if (eventsInFlight_)
		{
			return;
		}
		eventsInFlight_ = true;
		fx.http.push_back(get("events", sessionPath("/events?after_seq=" + std::to_string(seq_.cursor()) + "&limit=500"), true));
	}

	void onEventsPage(const HttpResult& r, const json::Value& body, Effects& fx)
	{
		eventsInFlight_ = false;
		if (r.transportFailed || r.status != 200)
		{
			beginRecover(fx, "events_page_failed");
			return;
		}
		if (body["resync_required"].asBool())
		{
			beginRecover(fx, "events_expired");
			return;
		}
		pushEvents(body["events"].items(), fx);
		if (body["has_more"].asBool())
		{
			fetchEvents(fx);
		}
	}

	void onObject(const std::string& id, const HttpResult& r, const json::Value& body, Effects& fx)
	{
		objectInFlight_.erase(id);
		if (r.status == 200)
		{
			mirror_.ApplyObjectDetail(body);
			Notice n = note(NoticeKind::EventApplied, "object.refreshed");
			n.ids.push_back(id);
			fx.notices.push_back(std::move(n));
		}
		else if (r.status == 404)
		{
			requestSnapshot(fx, "object_gone");
		}
		else if (r.transportFailed || r.status >= 500)
		{
			requestSnapshot(fx, "object_refresh_failed");
		}
	}

	double clockSyncInterval() const
	{
		const double tps = mirror_.model().clock.ticksPerSecond;
		const double perTick = tps > 0.0 ? 1.0 / tps : cfg_.clockSyncMaxSeconds;
		return std::min(cfg_.clockSyncMaxSeconds, std::max(cfg_.clockSyncMinSeconds, perTick));
	}

	void armClockSync(Effects& fx)
	{
		if (!syncTimerArmed_ && clockRunning() && state_ != SessionState::Failed)
		{
			syncTimerArmed_ = true;
			fx.timers.push_back({"clock_sync", clockSyncInterval()});
		}
	}

	void onSync(const HttpResult& r, const json::Value& body, Effects& fx)
	{
		syncInFlight_ = false;
		if (r.transportFailed || r.status >= 500)
		{
			return;  // the next tick retries; the socket/restore path covers outages
		}
		if (r.status != 200)
		{
			if (r.status == 403 || r.status == 404)
			{
				fail(fx, "session_invalid");
			}
			return;
		}
		pushEvents(body["events"].items(), fx);
	}

	// ---------------------------------------------------------------- commands
	void pump(Effects& fx)
	{
		if (state_ != SessionState::Ready || ledger_.busy() || queue_.empty())
		{
			return;
		}
		QueuedIntent q = queue_.front();
		queue_.pop_front();
		CommandContext ctx;
		ctx.sessionId = creds_.sessionId;
		ctx.timelineId = mirror_.model().timelineId;
		ctx.expectedStateVersion = mirror_.model().stateVersion;
		if (forceStale_)
		{
			forceStale_ = false;
			ctx.expectedStateVersion = std::max<int64_t>(1, ctx.expectedStateVersion - 1);
		}
		if (!ledger_.Begin(q.localId, q.intent, ctx, q.staleResubmits))
		{
			queue_.push_front(q);
			return;
		}
		cmdBackoff_.Reset();
		resendPending(fx);
	}

	void resendPending(Effects& fx)
	{
		const PendingCommand* p = ledger_.pending();
		if (!p)
		{
			return;
		}
		HttpEffect h;
		h.tag = "command";
		h.method = "POST";
		h.path = sessionPath("/commands");
		h.body = ledger_.NextAttempt();
		h.authorized = true;
		h.timeoutSeconds = cfg_.commandTimeoutSeconds;
		h.headers.emplace_back("Idempotency-Key", p->ids.idempotencyKey);
		lastCommand_ = p->intent.action + " " + p->intent.target + " #" + std::to_string(p->attempts);
		fx.http.push_back(std::move(h));
		fx.notices.push_back(note(NoticeKind::CommandSent, std::to_string(p->attempts), p->localId));
	}

	void onCommand(const HttpResult& r, const json::Value& body, Effects& fx)
	{
		const CommandOutcome out = ClassifyCommandResponse(r.transportFailed, r.status, body, r.replayedHeader);
		if (out.kind == CommandOutcomeKind::RetrySameKey)
		{
			fx.timers.push_back({"command_retry", cmdBackoff_.Next()});
			return;
		}
		PendingCommand done;
		ledger_.Resolve(out, &done);
		lastCommand_ = done.intent.action + " " + done.intent.target + " → " + ToString(out.kind);
		if (out.kind == CommandOutcomeKind::Applied || out.kind == CommandOutcomeKind::NoChange)
		{
			pushEvents(out.result["events"].items(), fx);
			if (out.kind == CommandOutcomeKind::Applied)
			{
				// Some authoritative changes have no event in odyssey.game.v1 (the player's semantic
				// location and visited flags after world.zone_entered, verified against the live
				// backend). Never inferred from the action: one coalesced snapshot per applied command.
				requestSnapshot(fx, "post_command");
			}
			Notice n = note(NoticeKind::CommandResolved, ToString(out.kind), done.localId);
			n.data = out.result;
			fx.notices.push_back(std::move(n));
		}
		else if (out.kind == CommandOutcomeKind::Stale)
		{
			pendingStale_ = true;
			stale_ = {done.localId, done.intent, done.staleResubmits};
			staleServerVersion_ = out.stateVersion;
			requestSnapshot(fx, "stale_state");
			Notice n = note(NoticeKind::CommandResolved, ToString(out.kind), done.localId);
			n.data = body;
			fx.notices.push_back(std::move(n));
			return;  // do not pump: the refresh decides first
		}
		else
		{
			Notice n = note(NoticeKind::CommandResolved, ToString(out.kind), done.localId);
			n.data = body;
			fx.notices.push_back(std::move(n));
			if (out.kind == CommandOutcomeKind::SessionInvalid)
			{
				fx.notices.push_back(note(NoticeKind::SessionInvalid, out.error.reason));
				fail(fx, "session_invalid");
				return;
			}
			if (out.kind == CommandOutcomeKind::MissionComplete)
			{
				requestSnapshot(fx, "mission_complete");
			}
		}
		pump(fx);
	}

	// After STALE_STATE and a fresh snapshot: re-submit once, with NEW ids, only if the backend
	// still offers the action for the target; otherwise the intent is superseded.
	void reconcileStale(Effects& fx)
	{
		pendingStale_ = false;
		const QueuedIntent q = stale_;
		if (q.intent.resubmitAfterStale && q.staleResubmits < 1 && stillOffered(q.intent))
		{
			queue_.push_front({q.localId, q.intent, q.staleResubmits + 1});
		}
		else
		{
			fx.notices.push_back(note(NoticeKind::CommandSuperseded, q.intent.action, q.localId));
		}
	}

	bool stillOffered(const SemanticIntent& in) const
	{
		const MirrorModel& m = mirror_.model();
		if (in.target.empty())
		{
			return true;
		}
		if (const LocationInfo* l = m.location(in.target))
		{
			return l->access == "open";
		}
		if (const ObjectInfo* o = m.object(in.target))
		{
			const InteractionInfo* i = o->interaction(in.action);
			// container-targeted actions (transfers) are validated by the backend, not offered
			return i ? i->available : m.container(in.target) != nullptr;
		}
		return m.crewMember(in.target) != nullptr;
	}

	void onAnalysis(NoticeKind kind, const HttpResult& r, const json::Value& body, Effects& fx)
	{
		Notice n = note(r.status == 200 ? kind : NoticeKind::Error,
			r.status == 200 ? "" : "analysis_status_" + std::to_string(r.status));
		n.data = body;
		fx.notices.push_back(std::move(n));
	}

	ClientConfig cfg_;
	SessionState state_ = SessionState::Idle;
	Credentials creds_;
	json::Value features_;
	StateMirror mirror_;
	EventSequencer seq_;
	CommandLedger ledger_;
	Backoff backoff_;
	Backoff cmdBackoff_;
	std::deque<QueuedIntent> queue_;
	QueuedIntent stale_{0, {}, 0};
	std::set<std::string> objectInFlight_;
	std::string snapshotReason_;
	std::string lastCommand_;
	uint64_t nextLocalId_ = 0;
	int reconnects_ = 0;
	bool wsOpen_ = false, wsConnecting_ = false, shuttingDown_ = false, readyOnce_ = false;
	bool restoreInFlight_ = false, snapshotInFlight_ = false, snapshotAgain_ = false, eventsInFlight_ = false;
	bool syncInFlight_ = false, syncTimerArmed_ = false, resourceTimerArmed_ = false, gapTimerArmed_ = false;
	bool pendingStale_ = false, forceStale_ = false;
	int64_t staleServerVersion_ = 0;
	bool resourcesStale_ = false;
};

}  // namespace odyssey
