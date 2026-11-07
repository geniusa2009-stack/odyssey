#pragma once

#include "OdysseyProtocol/Json.h"
#include "OdysseyProtocol/Protocol.h"

#include <cstdint>
#include <iterator>
#include <map>
#include <string>
#include <utility>
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

inline EnvelopeProblem CheckEnvelope(const json::Value& envelope, const std::string& sessionId)
{
	if (!envelope.isObject()) return EnvelopeProblem::NotAnObject;
	if (!CheckProtocol(envelope).ok) return EnvelopeProblem::ProtocolMismatch;
	if (!sessionId.empty() && envelope["session_id"].asString() != sessionId) return EnvelopeProblem::WrongSession;
	if (!envelope["seq"].isInt() || envelope["seq"].asInt() < 1) return EnvelopeProblem::MissingSeq;
	return EnvelopeProblem::None;
}

inline bool IsControlFrame(const json::Value& message)
{
	const std::string& type = message["type"].asString();
	return !message.has("seq") && (type == "CONNECTED" || type == "RESUMED" || type == "RESYNC_REQUIRED" || type == "PONG");
}

struct SequencerResult
{
	std::vector<json::Value> ready;
	int duplicates = 0;
	bool held = false;
	bool needsRestore = false;
	EnvelopeProblem rejected = EnvelopeProblem::None;
};

class EventSequencer
{
	using Sequence = int64_t;
	using Queue = std::map<Sequence, json::Value>;

public:
	explicit EventSequencer(size_t maxHeld = 64) noexcept : maxHeld_(maxHeld) {}

	void Reset(Sequence cursor)
	{
		cursor_ = cursor;
		held_.erase(held_.begin(), held_.upper_bound(cursor_));
	}

	Sequence cursor() const noexcept { return cursor_; }
	size_t heldCount() const noexcept { return held_.size(); }
	Sequence firstMissing() const noexcept { return cursor_ + 1; }
	uint64_t duplicatesDropped() const noexcept { return duplicatesTotal_; }

	SequencerResult Push(const json::Value& envelope, const std::string& sessionId)
	{
		SequencerResult result;
		result.rejected = CheckEnvelope(envelope, sessionId);
		if (result.rejected != EnvelopeProblem::None) return result;

		const Sequence sequence = envelope["seq"].asInt();
		if (sequence <= cursor_ || held_.find(sequence) != held_.end())
		{
			++result.duplicates;
			++duplicatesTotal_;
			return result;
		}

		held_.try_emplace(sequence, envelope);
		Drain(result);
		Finalize(result);
		return result;
	}

	SequencerResult PushAll(const std::vector<json::Value>& envelopes, const std::string& sessionId)
	{
		SequencerResult aggregate;
		for (const auto& envelope : envelopes)
		{
			SequencerResult current = Push(envelope, sessionId);
			aggregate.ready.insert(aggregate.ready.end(), std::make_move_iterator(current.ready.begin()), std::make_move_iterator(current.ready.end()));
			aggregate.duplicates += current.duplicates;
			if (current.rejected != EnvelopeProblem::None) aggregate.rejected = current.rejected;
		}
		Finalize(aggregate);
		return aggregate;
	}

private:
	void Drain(SequencerResult& result)
	{
		for (auto it = held_.begin(); it != held_.end() && it->first == cursor_ + 1;)
		{
			result.ready.emplace_back(std::move(it->second));
			++cursor_;
			it = held_.erase(it);
		}
	}

	void Finalize(SequencerResult& result) const noexcept
	{
		result.held = !held_.empty();
		result.needsRestore = held_.size() > maxHeld_;
	}

	size_t maxHeld_;
	Sequence cursor_ = 0;
	uint64_t duplicatesTotal_ = 0;
	Queue held_;
};

}
