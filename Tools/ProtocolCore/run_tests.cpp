// Native runner for the shared odyssey.game.v1 protocol test cases (no Unreal Engine needed).
// Built with Unreal-like constraints: -fno-exceptions -fno-rtti -Wshadow -Werror (see Makefile).
//   make -C Tools/ProtocolCore test            # from the project root
//   Tools/ProtocolCore/build/run_tests [--root <project root>] [--filter <substring>]
// Unreal defines these as function-like macros; defining them the same way here makes any
// identifier collision in the shared headers a native compile error instead of a UE-only surprise.
#define check(expr) ODYSSEY_UE_MACRO_COLLISION_check
#define checkf(expr, ...) ODYSSEY_UE_MACRO_COLLISION_checkf
#define verify(expr) ODYSSEY_UE_MACRO_COLLISION_verify
#define ensure(expr) ODYSSEY_UE_MACRO_COLLISION_ensure
#define TEXT(x) ODYSSEY_UE_MACRO_COLLISION_TEXT
#include "Tests/ProtocolTestCases.h"
#undef check
#undef checkf
#undef verify
#undef ensure
#undef TEXT

#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>

namespace
{
class NativeContext final : public odyssey::tests::Context
{
public:
	explicit NativeContext(std::string root) : root_(std::move(root)) {}
	void Check(bool ok, const char* expr, const char* file, int line) override
	{
		++checks;
		if (!ok)
		{
			++failures;
			const char* base = std::strrchr(file, '/');
			std::printf("    FAIL %s:%d  %s\n", base ? base + 1 : file, line, expr);
		}
	}
	bool ReadFile(const std::string& relativePath, std::string& out) override
	{
		std::ifstream f(root_ + "/" + relativePath, std::ios::binary);
		if (!f)
		{
			std::printf("    cannot read %s\n", relativePath.c_str());
			return false;
		}
		std::ostringstream ss;
		ss << f.rdbuf();
		out = ss.str();
		return true;
	}
	int checks = 0;
	int failures = 0;

private:
	std::string root_;
};
}  // namespace

int main(int argc, char** argv)
{
	std::string root = ".";
	std::string filter;
	for (int i = 1; i + 1 < argc; i += 2)
	{
		if (std::strcmp(argv[i], "--root") == 0) root = argv[i + 1];
		else if (std::strcmp(argv[i], "--filter") == 0) filter = argv[i + 1];
	}
	int failedCases = 0, ran = 0, totalChecks = 0;
	for (const odyssey::tests::Case& c : odyssey::tests::AllCases())
	{
		if (!filter.empty() && std::string(c.name).find(filter) == std::string::npos) continue;
		NativeContext ctx(root);
		c.fn(ctx);
		++ran;
		totalChecks += ctx.checks;
		std::printf("%s %-46s %d checks\n", ctx.failures ? "FAIL" : "ok  ", c.name, ctx.checks);
		failedCases += ctx.failures ? 1 : 0;
	}
	std::printf("\n%d/%d cases passed, %d checks\n", ran - failedCases, ran, totalChecks);
	return failedCases == 0 && ran > 0 ? 0 : 1;
}
