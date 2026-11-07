// ODYSSEY protocol core — realtime event ordering, de-duplication and the resume cursor.
//
// The backend guarantees a gap-free, strictly increasing per-session `seq`. Events can still
// arrive twice (socket backlog + command response carry the same event) or out of order (a
// command response overtakes the socket). The sequencer:
//   * applies events strictly in seq order, exactly once;
//   * drops duplicates (seq <= cursor);
//   * holds early events (seq > cursor + 1) until the gap is filled, up to a bound;
//   * reports when the client must fetch the gap (REST events page) or restore;
//   * exposes the resume cursor (= last applied seq) for reconnects.
#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace odyssey
{

enum class EnvelopeProblem : uint8_t
{
	None,
	NotAnObject,
	ProtocolMismatch,
	WrongSession,
	MissingSeq,
};

inline EnvelopeProblem CheckEnvelope(const json::Value& env, const std::string& sessionId)
{
	if (!env.isObject())
	{
		return EnvelopeProblem::NotAnObject;
	}
	if (!CheckProtocol(env).ok)
	{
		return EnvelopeProblem::ProtocolMismatch;
	}
	if (!sessionId.empty() && env["session_id"].asString() != sessionId)
	{
		return EnvelopeProblem::WrongSession;
	}
	if (!env["seq"].isInt() || env["seq"].asInt() < 1)
	{
		return EnvelopeProblem::MissingSeq;
	}
	return EnvelopeProblem::None;
}

// Control frames share the "type" field with events but have no "seq".
inline bool IsControlFrame(const json::Value& msg)
{
	const std::string& t = msg["type"].asString();
	return !msg.has("seq") && (t == "CONNECTED" || t == "RESUMED" || t == "RESYNC_REQUIRED" || t == "PONG");
}

struct SequencerResult
{
	std::vector<json::Value> ready;  // events to apply now, in order
	int duplicates = 0;
	bool held = false;          // an early event is waiting for a gap to be filled
	bool needsRestore = false;  // the gap cannot be filled from the socket: fetch/restore
	EnvelopeProblem rejected = EnvelopeProblem::None;
};

class EventSequencer
{
public:
	explicit EventSequencer(size_t maxHeld = 64) : maxHeld_(maxHeld) {}

	// After a snapshot/restore the cursor is the snapshot's session.last_seq: everything at or
	// below it is already reflected in the snapshot.
	void Reset(int64_t cursor)
	{
		cursor_ = cursor;
		for (auto it = held_.begin(); it != held_.end();)
		{
			it = it->first <= cursor_ ? held_.erase(it) : std::next(it);
		}
	}

	int64_t cursor() const { return cursor_; }
	size_t heldCount() const { return held_.size(); }
	int64_t firstMissing() const { return cursor_ + 1; }
	uint64_t duplicatesDropped() const { return duplicatesTotal_; }

	SequencerResult Push(const json::Value& env, const std::string& sessionId)
	{
		SequencerResult r;
		r.rejected = CheckEnvelope(env, sessionId);
		if (r.rejected != EnvelopeProblem::None)
		{
			return r;
		}
		const int64_t seq = env["seq"].asInt();
		if (seq <= cursor_ || held_.count(seq))
		{
			++r.duplicates;
			++duplicatesTotal_;
			return r;
		}
		held_.emplace(seq, env);
		drain(r);
		if (!held_.empty())
		{
			r.held = true;
			r.needsRestore = held_.size() > maxHeld_;
		}
		return r;
	}

	// Push several (e.g. a REST events page or a command response) and collect what is ready.
	SequencerResult PushAll(const std::vector<json::Value>& envs, const std::string& sessionId)
	{
		SequencerResult total;
		for (const json::Value& e : envs)
		{
			SequencerResult r = Push(e, sessionId);
			for (json::Value& v : r.ready)
			{
				total.ready.push_back(std::move(v));
			}
			total.duplicates += r.duplicates;
			if (r.rejected != EnvelopeProblem::None)
			{
				total.rejected = r.rejected;
			}
		}
		total.held = !held_.empty();
		total.needsRestore = held_.size() > maxHeld_;
		return total;
	}

private:
	void drain(SequencerResult& r)
	{
		while (!held_.empty() && held_.begin()->first == cursor_ + 1)
		{
			r.ready.push_back(std::move(held_.begin()->second));
			held_.erase(held_.begin());
			++cursor_;
		}
	}

	size_t maxHeld_;
	int64_t cursor_ = 0;
	uint64_t duplicatesTotal_ = 0;
	std::map<int64_t, json::Value> held_;
};

}  // namespace odyssey
