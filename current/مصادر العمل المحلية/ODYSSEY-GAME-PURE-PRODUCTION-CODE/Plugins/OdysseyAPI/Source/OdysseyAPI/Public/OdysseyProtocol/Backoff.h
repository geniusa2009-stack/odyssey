#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace odyssey
{

struct BackoffPolicy
{
	double initialSeconds = 0.5;
	double maxSeconds = 15.0;
	double factor = 2.0;
	double jitter = 0.2;
};

class Backoff
{
public:
	explicit Backoff(BackoffPolicy policy = {}, uint64_t seed = 0x0D15EA5Eull) noexcept
		: policy_(policy), state_(seed ? seed : 1) {}

	double Next() noexcept
	{
		const double exponent = std::pow(policy_.factor, static_cast<double>(attempts_++));
		const double base = std::min(policy_.maxSeconds, policy_.initialSeconds * exponent);
		const double centered = 2.0 * Unit() - 1.0;
		return std::max(0.0, base * (1.0 + policy_.jitter * centered));
	}

	void Reset() noexcept { attempts_ = 0; }
	int attempts() const noexcept { return attempts_; }

private:
	uint64_t NextRandom() noexcept
	{
		state_ ^= state_ >> 12;
		state_ ^= state_ << 25;
		state_ ^= state_ >> 27;
		return state_ * 2685821657736338717ull;
	}

	double Unit() noexcept
	{
		return static_cast<double>(NextRandom() % 10001) / 10000.0;
	}

	BackoffPolicy policy_;
	uint64_t state_;
	int attempts_ = 0;
};

}
