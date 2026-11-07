# Native build of the engine-independent odyssey.game.v1 client core and its tests.
# Flags mirror Unreal's defaults for module code: no exceptions, no RTTI, shadowing is an error.
#   make test        clang++ (the compiler family Unreal uses on macOS), strict warnings
#   make test-asan   g++ with AddressSanitizer + UBSan (memory/UB check of the same code)
#   make live        build the live harness (see live_harness.cpp / run_live.sh)
ROOT := $(abspath ../..)
API := $(ROOT)/Plugins/OdysseyAPI/Source/OdysseyAPI
COMMON := -std=c++20 -g -fno-exceptions -fno-rtti -Wall -Wextra -Wshadow -Wno-unused-parameter -Werror \
	-I$(API)/Public -I$(API)/Private
SAN := -fsanitize=address,undefined -fno-sanitize-recover=all
HEADERS := $(wildcard $(API)/Public/OdysseyProtocol/*.h) $(wildcard $(API)/Private/Tests/*.h)

build/run_tests: run_tests.cpp $(HEADERS)
	@mkdir -p build
	clang++ $(COMMON) -O2 run_tests.cpp -o $@

build/run_tests_asan: run_tests.cpp $(HEADERS)
	@mkdir -p build
	g++ $(COMMON) -O1 $(SAN) run_tests.cpp -o $@

build/live_harness: live_harness.cpp $(HEADERS)
	@mkdir -p build
	clang++ $(COMMON) -O1 live_harness.cpp -o $@

test: build/run_tests
	./build/run_tests --root $(ROOT)

test-asan: build/run_tests_asan
	./build/run_tests_asan --root $(ROOT)

live: build/live_harness

clean:
	rm -rf build

.PHONY: test test-asan live clean
