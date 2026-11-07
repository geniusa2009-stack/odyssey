// ODYSSEY protocol core — exponential reconnect/retry backoff with deterministic jitter.
#pragma once

#include <algorithm>
#include <cstdint>

namespace odyssey
{

struct BackoffPolicy
{
	double initialSeconds = 0.5;
	double maxSeconds = 15.0;
	double factor = 2.0;
	double jitter = 0.2;  // ±20 %
};

class Backoff
{
public:
	explicit Backoff(BackoffPolicy p = {}, uint64_t seed = 0x0D15EA5Eull) : p_(p), state_(seed ? seed : 1) {}

	// Delay before the next attempt; grows until Reset().
	double Next()
	{
		double base = p_.initialSeconds;
		for (int i = 0; i < attempts_ && base < p_.maxSeconds; ++i)
		{
			base *= p_.factor;
		}
		base = std::min(base, p_.maxSeconds);
		++attempts_;
		const double unit = static_cast<double>(nextRandom() % 10001) / 10000.0;  // [0, 1]
		return std::max(0.0, base * (1.0 + p_.jitter * (2.0 * unit - 1.0)));
	}
	void Reset() { attempts_ = 0; }
	int attempts() const { return attempts_; }

private:
	uint64_t nextRandom()
	{
		// xorshift64*: deterministic for tests, good enough for jitter
		state_ ^= state_ >> 12;
		state_ ^= state_ << 25;
		state_ ^= state_ >> 27;
		return state_ * 2685821657736338717ull;
	}

	BackoffPolicy p_;
	uint64_t state_;
	int attempts_ = 0;
};

}  // namespace odyssey
