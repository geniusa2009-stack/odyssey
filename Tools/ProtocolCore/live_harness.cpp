// Live contract harness: runs the engine-independent odyssey.game.v1 client (SessionMachine) through
// a minimal POSIX HTTP/1.1 + WebSocket shell against a REAL backend process, and plays the Earth
// Command slice end to end with fault injection:
//   * a command whose response is lost (timeout) → same Idempotency-Key retried → replayed answer
//   * realtime frames duplicated and delivered out of order
//   * a forced STALE_STATE → snapshot → reconciled resubmission with new ids
//   * the WebSocket dropped mid-session → HTTP restore → resume
//   * the backend process stopped and restarted (same database) → backoff → restore → resume
//   * a second client process restoring from persisted credentials
// After each step the local mirror is compared with a fresh authoritative snapshot (MirrorDiff).
//
// This is NOT the Unreal transport. It validates the protocol core and the backend together;
// the Unreal shell (FHttpModule / IWebSocketsModule) is UNREAL_EDITOR_VERIFICATION_REQUIRED.
//
//   Tools/ProtocolCore/run_live.sh            (starts the backend, builds and runs this)
//   build/live_harness --port 8765 --root <project> --start-cmd "<cmd>" --stop-cmd "<cmd>"
#include "OdysseyProtocol/MirrorDiff.h"
#include "OdysseyProtocol/SemanticRegistry.h"
#include "OdysseyProtocol/SessionMachine.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <random>
#include <sstream>
#include <string>
#include <vector>

using namespace odyssey;

namespace
{
// ------------------------------------------------------------------ utilities
double Now()
{
	using namespace std::chrono;
	return duration<double>(steady_clock::now().time_since_epoch()).count();
}

std::string Base64(const uint8_t* data, size_t n)
{
	static const char* t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
	std::string out;
	for (size_t i = 0; i < n; i += 3)
	{
		uint32_t v = static_cast<uint32_t>(data[i]) << 16;
		if (i + 1 < n) v |= static_cast<uint32_t>(data[i + 1]) << 8;
		if (i + 2 < n) v |= data[i + 2];
		out += t[(v >> 18) & 63];
		out += t[(v >> 12) & 63];
		out += i + 1 < n ? t[(v >> 6) & 63] : '=';
		out += i + 2 < n ? t[v & 63] : '=';
	}
	return out;
}

std::array<uint8_t, 20> Sha1(const std::string& msg)
{
	uint32_t h[5] = {0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0};
	std::string m = msg;
	const uint64_t bits = static_cast<uint64_t>(msg.size()) * 8;
	m += static_cast<char>(0x80);
	while (m.size() % 64 != 56) m += '\0';
	for (int i = 7; i >= 0; --i) m += static_cast<char>((bits >> (8 * i)) & 0xFF);
	auto rol = [](uint32_t v, int s) { return (v << s) | (v >> (32 - s)); };
	for (size_t c = 0; c < m.size(); c += 64)
	{
		uint32_t w[80];
		for (int i = 0; i < 16; ++i)
		{
			w[i] = (static_cast<uint32_t>(static_cast<uint8_t>(m[c + 4 * i])) << 24) |
				   (static_cast<uint32_t>(static_cast<uint8_t>(m[c + 4 * i + 1])) << 16) |
				   (static_cast<uint32_t>(static_cast<uint8_t>(m[c + 4 * i + 2])) << 8) |
				   static_cast<uint32_t>(static_cast<uint8_t>(m[c + 4 * i + 3]));
		}
		for (int i = 16; i < 80; ++i) w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
		uint32_t a = h[0], b = h[1], cc = h[2], dd = h[3], e = h[4];
		for (int i = 0; i < 80; ++i)
		{
			uint32_t f, k;
			if (i < 20) { f = (b & cc) | (~b & dd); k = 0x5A827999; }
			else if (i < 40) { f = b ^ cc ^ dd; k = 0x6ED9EBA1; }
			else if (i < 60) { f = (b & cc) | (b & dd) | (cc & dd); k = 0x8F1BBCDC; }
			else { f = b ^ cc ^ dd; k = 0xCA62C1D6; }
			const uint32_t tmp = rol(a, 5) + f + e + k + w[i];
			e = dd; dd = cc; cc = rol(b, 30); b = a; a = tmp;
		}
		h[0] += a; h[1] += b; h[2] += cc; h[3] += dd; h[4] += e;
	}
	std::array<uint8_t, 20> out{};
	for (int i = 0; i < 5; ++i)
		for (int j = 0; j < 4; ++j) out[4 * i + j] = static_cast<uint8_t>((h[i] >> (24 - 8 * j)) & 0xFF);
	return out;
}

int Connect(int port, double timeoutSeconds)
{
	const int fd = ::socket(AF_INET, SOCK_STREAM, 0);
	if (fd < 0) return -1;
	sockaddr_in addr{};
	addr.sin_family = AF_INET;
	addr.sin_port = htons(static_cast<uint16_t>(port));
	addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
	timeval tv{static_cast<long>(timeoutSeconds), static_cast<long>((timeoutSeconds - static_cast<long>(timeoutSeconds)) * 1e6)};
	::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
	::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
	int one = 1;
	::setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
	if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0)
	{
		::close(fd);
		return -1;
	}
	return fd;
}

bool SendAll(int fd, const std::string& s)
{
	size_t off = 0;
	while (off < s.size())
	{
		const ssize_t n = ::send(fd, s.data() + off, s.size() - off, MSG_NOSIGNAL);
		if (n <= 0) return false;
		off += static_cast<size_t>(n);
	}
	return true;
}

std::string Lower(std::string s)
{
	for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
	return s;
}

struct RawResponse
{
	bool ok = false;
	int status = 0;
	std::map<std::string, std::string> headers;  // lower-case names
	std::string body;
};

RawResponse HttpRequest(int port, const std::string& method, const std::string& path, const std::string& body,
	const std::vector<std::pair<std::string, std::string>>& headers, double timeout)
{
	RawResponse out;
	const int fd = Connect(port, timeout);
	if (fd < 0) return out;
	std::ostringstream req;
	req << method << " " << path << " HTTP/1.1\r\nHost: 127.0.0.1:" << port
		<< "\r\nAccept: application/json\r\nConnection: close\r\nUser-Agent: OdysseyProtocolHarness/1\r\n";
	for (const auto& h : headers) req << h.first << ": " << h.second << "\r\n";
	if (method == "POST") req << "Content-Type: application/json\r\nContent-Length: " << body.size() << "\r\n";
	req << "\r\n" << body;
	if (!SendAll(fd, req.str()))
	{
		::close(fd);
		return out;
	}
	std::string raw;
	char buf[16384];
	for (;;)
	{
		const ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
		if (n < 0)
		{
			::close(fd);
			return out;  // timeout or reset: transport failure
		}
		if (n == 0) break;
		raw.append(buf, static_cast<size_t>(n));
	}
	::close(fd);
	const size_t headEnd = raw.find("\r\n\r\n");
	if (headEnd == std::string::npos || raw.compare(0, 9, "HTTP/1.1 ") != 0) return out;
	out.status = std::atoi(raw.c_str() + 9);
	std::istringstream hs(raw.substr(0, headEnd));
	std::string line;
	std::getline(hs, line);
	while (std::getline(hs, line))
	{
		if (!line.empty() && line.back() == '\r') line.pop_back();
		const size_t colon = line.find(':');
		if (colon == std::string::npos) continue;
		std::string v = line.substr(colon + 1);
		while (!v.empty() && v.front() == ' ') v.erase(0, 1);
		out.headers[Lower(line.substr(0, colon))] = v;
	}
	std::string rest = raw.substr(headEnd + 4);
	if (Lower(out.headers["transfer-encoding"]) == "chunked")
	{
		std::string decoded;
		size_t p = 0;
		for (;;)
		{
			const size_t eol = rest.find("\r\n", p);
			if (eol == std::string::npos) return out;
			const size_t len = std::strtoul(rest.substr(p, eol - p).c_str(), nullptr, 16);
			if (len == 0) break;
			decoded += rest.substr(eol + 2, len);
			p = eol + 2 + len + 2;
		}
		rest = decoded;
	}
	out.body = rest;
	out.ok = true;
	return out;
}

// ------------------------------------------------------------------ WebSocket client (RFC 6455)
class WebSocket
{
public:
	bool Open(int port, const std::string& path, const std::string& authorization, std::string& err)
	{
		fd_ = Connect(port, 5.0);
		if (fd_ < 0) { err = "connect"; return false; }
		std::array<uint8_t, 16> nonce{};
		for (auto& b : nonce) b = static_cast<uint8_t>(rng_());
		const std::string key = Base64(nonce.data(), nonce.size());
		std::ostringstream req;
		req << "GET " << path << " HTTP/1.1\r\nHost: 127.0.0.1:" << port
			<< "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: " << key
			<< "\r\nAuthorization: " << authorization << "\r\n\r\n";
		if (!SendAll(fd_, req.str())) { err = "send"; Close(); return false; }
		std::string head;
		char c;
		while (head.find("\r\n\r\n") == std::string::npos)
		{
			if (::recv(fd_, &c, 1, 0) != 1) { err = "handshake_read"; Close(); return false; }
			head += c;
		}
		if (head.compare(0, 12, "HTTP/1.1 101") != 0) { err = "status:" + head.substr(0, head.find("\r\n")); Close(); return false; }
		const auto digest = Sha1(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11");
		if (Lower(head).find(Lower("sec-websocket-accept: " + Base64(digest.data(), digest.size()))) == std::string::npos)
		{
			err = "bad_accept";
			Close();
			return false;
		}
		const int flags = ::fcntl(fd_, F_GETFL, 0);
		::fcntl(fd_, F_SETFL, flags | O_NONBLOCK);
		return true;
	}
	bool IsOpen() const { return fd_ >= 0; }
	int fd() const { return fd_; }
	void Close()
	{
		if (fd_ >= 0) ::close(fd_);
		fd_ = -1;
		buf_.clear();
	}
	bool SendText(const std::string& text) { return SendFrame(0x1, text); }

	// Reads what is available. Returns false when the connection closed (closeCode set).
	bool Read(std::vector<std::string>& texts, int& closeCode)
	{
		char tmp[65536];
		for (;;)
		{
			const ssize_t n = ::recv(fd_, tmp, sizeof(tmp), 0);
			if (n > 0) { buf_.append(tmp, static_cast<size_t>(n)); continue; }
			if (n == 0) { closeCode = 1006; Close(); return false; }
			if (errno == EAGAIN || errno == EWOULDBLOCK) break;
			closeCode = 1006;
			Close();
			return false;
		}
		for (;;)
		{
			if (buf_.size() < 2) return true;
			const uint8_t b0 = static_cast<uint8_t>(buf_[0]), b1 = static_cast<uint8_t>(buf_[1]);
			uint64_t len = b1 & 0x7F;
			size_t hdr = 2;
			if (len == 126) { if (buf_.size() < 4) return true; len = (static_cast<uint8_t>(buf_[2]) << 8) | static_cast<uint8_t>(buf_[3]); hdr = 4; }
			else if (len == 127)
			{
				if (buf_.size() < 10) return true;
				len = 0;
				for (int i = 0; i < 8; ++i) len = (len << 8) | static_cast<uint8_t>(buf_[2 + i]);
				hdr = 10;
			}
			if (buf_.size() < hdr + len) return true;
			const std::string payload = buf_.substr(hdr, static_cast<size_t>(len));
			buf_.erase(0, hdr + static_cast<size_t>(len));
			const int op = b0 & 0x0F;
			const bool fin = (b0 & 0x80) != 0;
			if (op == 0x1 || op == 0x0)
			{
				partial_ += payload;
				if (fin) { texts.push_back(partial_); partial_.clear(); }
			}
			else if (op == 0x8)
			{
				closeCode = payload.size() >= 2 ? (static_cast<uint8_t>(payload[0]) << 8) | static_cast<uint8_t>(payload[1]) : 1005;
				SendFrame(0x8, payload.substr(0, 2));
				Close();
				return false;
			}
			else if (op == 0x9)
			{
				SendFrame(0xA, payload);
			}
		}
	}

private:
	bool SendFrame(int op, const std::string& payload)
	{
		if (fd_ < 0) return false;
		std::string f;
		f += static_cast<char>(0x80 | op);
		const size_t n = payload.size();
		if (n < 126) f += static_cast<char>(0x80 | n);
		else if (n < 65536) { f += static_cast<char>(0x80 | 126); f += static_cast<char>(n >> 8); f += static_cast<char>(n & 0xFF); }
		else { f += static_cast<char>(0x80 | 127); for (int i = 7; i >= 0; --i) f += static_cast<char>((static_cast<uint64_t>(n) >> (8 * i)) & 0xFF); }
		uint8_t mask[4];
		for (auto& m : mask) m = static_cast<uint8_t>(rng_());
		f.append(reinterpret_cast<char*>(mask), 4);
		for (size_t i = 0; i < n; ++i) f += static_cast<char>(payload[i] ^ mask[i % 4]);
		const int flags = ::fcntl(fd_, F_GETFL, 0);
		::fcntl(fd_, F_SETFL, flags & ~O_NONBLOCK);
		const bool ok = SendAll(fd_, f);
		::fcntl(fd_, F_SETFL, flags);
		return ok;
	}
	int fd_ = -1;
	std::string buf_, partial_;
	std::mt19937 rng_{std::random_device{}()};
};

// ------------------------------------------------------------------ the shell
struct Stats
{
	int http = 0, http429 = 0, commandsSent = 0, replayedAnswers = 0, wsFramesIn = 0, wsConnects = 0;
	int injectedDuplicates = 0, injectedSwaps = 0, injectedLostResponses = 0;
	std::map<std::string, int> notices;
};

std::string RandomUuid()
{
	static std::mt19937_64 rng{std::random_device{}()};
	std::array<uint8_t, 16> b{};
	for (auto& x : b) x = static_cast<uint8_t>(rng());
	return FormatUuidV4(b);
}

class Shell
{
public:
	Shell(int port, std::string name) : port_(port), name_(std::move(name)), m_(ClientConfig(), &RandomUuid) {}

	SessionMachine& machine() { return m_; }
	Stats stats;
	// fault injection
	int loseNextCommandResponses = 0;
	bool scrambleRealtime = false;
	std::vector<Notice> log;

	void Run(Effects fx) { process(std::move(fx)); }

	// Pumps the event loop until pred() or the deadline. Returns pred().
	bool PumpUntil(const std::function<bool()>& pred, double seconds)
	{
		const double end = Now() + seconds;
		while (!pred())
		{
			if (Now() > end) return false;
			step(std::min(0.05, std::max(0.0, end - Now())));
		}
		return true;
	}
	void PumpFor(double seconds)
	{
		PumpUntil([] { return false; }, seconds);
	}

	bool Saw(NoticeKind k, const std::string& detail = std::string(), size_t since = 0) const
	{
		for (size_t i = since; i < log.size(); ++i)
		{
			if (log[i].kind == k && (detail.empty() || log[i].detail == detail)) return true;
		}
		return false;
	}

	void KillSocket()
	{
		if (ws_.IsOpen())
		{
			::shutdown(ws_.fd(), SHUT_RDWR);
		}
	}

	// GET with the session token, outside the machine (verification only).
	json::Value AuthorizedGet(const std::string& path)
	{
		RawResponse r = HttpRequest(port_, "GET", path, "", {{"Authorization", m_.authorizationHeader()}}, 10.0);
		return r.ok && r.status == 200 ? json::parse(r.body).value : json::Value();
	}

private:
	void process(Effects fx)
	{
		std::vector<Effects> work;
		work.push_back(std::move(fx));
		while (!work.empty())
		{
			Effects cur = std::move(work.back());
			work.pop_back();
			std::vector<Effects> next;
			for (Notice& n : cur.notices)
			{
				++stats.notices[noticeName(n.kind)];
				log.push_back(n);
			}
			if (cur.wsClose && ws_.IsOpen()) ws_.Close();  // machine-initiated: no OnWsClosed
			for (const std::string& s : cur.wsSend) ws_.SendText(s);
			for (const TimerEffect& t : cur.timers) timers_[t.tag] = Now() + t.delaySeconds;  // one per tag
			for (const HttpEffect& h : cur.http) next.push_back(m_.OnHttpResponse(h.tag, execute(h)));
			for (const WsConnectEffect& w : cur.wsConnect)
			{
				std::string err;
				++stats.wsConnects;
				if (ws_.Open(port_, w.path, m_.authorizationHeader(), err)) next.push_back(m_.OnWsOpened());
				else next.push_back(m_.OnWsClosed(1006));
			}
			for (auto it = next.rbegin(); it != next.rend(); ++it) work.push_back(std::move(*it));
		}
	}

	HttpResult execute(const HttpEffect& h)
	{
		std::vector<std::pair<std::string, std::string>> headers = h.headers;
		if (h.authorized) headers.emplace_back("Authorization", m_.authorizationHeader());
		RawResponse r = HttpRequest(port_, h.method, h.path, h.body, headers, h.timeoutSeconds);
		++stats.http;
		HttpResult out;
		if (!r.ok)
		{
			out.transportFailed = true;
			return out;
		}
		stats.http429 += r.status == 429 ? 1 : 0;
		out.status = r.status;
		out.body = r.body;
		out.replayedHeader = r.headers["idempotent-replayed"] == "true";
		if (h.tag == "command")
		{
			++stats.commandsSent;
			stats.replayedAnswers += out.replayedHeader ? 1 : 0;
			if (loseNextCommandResponses > 0 && r.status == 200)
			{
				// the server applied it; the client never hears back (timeout after send)
				--loseNextCommandResponses;
				++stats.injectedLostResponses;
				HttpResult lost;
				lost.transportFailed = true;
				return lost;
			}
		}
		return out;
	}

	void step(double maxWait)
	{
		double wait = maxWait;
		for (const auto& t : timers_) wait = std::min(wait, std::max(0.0, t.second - Now()));
		if (ws_.IsOpen())
		{
			pollfd p{ws_.fd(), POLLIN, 0};
			::poll(&p, 1, static_cast<int>(wait * 1000));
			std::vector<std::string> texts;
			int code = 0;
			const bool open = ws_.Read(texts, code);
			deliver(texts);
			if (!open) process(m_.OnWsClosed(code));
		}
		else if (wait > 0)
		{
			::poll(nullptr, 0, static_cast<int>(wait * 1000));
		}
		if (!held_.empty() && Now() - heldAt_ > 0.3) flushHeld();
		const double now = Now();
		std::vector<std::string> due;
		for (const auto& t : timers_) if (t.second <= now) due.push_back(t.first);
		for (const std::string& tag : due)
		{
			timers_.erase(tag);
			process(m_.OnTimer(tag));
		}
	}

	void deliver(const std::vector<std::string>& texts)
	{
		for (const std::string& t : texts)
		{
			++stats.wsFramesIn;
			const bool isEvent = t.find("\"seq\"") != std::string::npos && t.find("\"event_id\"") != std::string::npos;
			if (!scrambleRealtime || !isEvent)
			{
				process(m_.OnWsText(t));
				continue;
			}
			if (held_.empty())
			{
				held_ = t;
				heldAt_ = Now();
				continue;
			}
			// deliver b, a, a(dup), b(dup): out of order and duplicated
			process(m_.OnWsText(t));
			process(m_.OnWsText(held_));
			process(m_.OnWsText(held_));
			process(m_.OnWsText(t));
			stats.injectedSwaps += 1;
			stats.injectedDuplicates += 2;
			held_.clear();
		}
	}
	void flushHeld()
	{
		const std::string h = held_;
		held_.clear();
		process(m_.OnWsText(h));
	}

	static const char* noticeName(NoticeKind k)
	{
		switch (k)
		{
		case NoticeKind::StateChanged: return "StateChanged";
		case NoticeKind::SessionReady: return "SessionReady";
		case NoticeKind::SnapshotApplied: return "SnapshotApplied";
		case NoticeKind::EventApplied: return "EventApplied";
		case NoticeKind::CommandQueued: return "CommandQueued";
		case NoticeKind::CommandSent: return "CommandSent";
		case NoticeKind::CommandResolved: return "CommandResolved";
		case NoticeKind::CommandSuperseded: return "CommandSuperseded";
		case NoticeKind::IntentRejected: return "IntentRejected";
		case NoticeKind::RestoreSummary: return "RestoreSummary";
		case NoticeKind::SessionReplaced: return "SessionReplaced";
		case NoticeKind::SessionInvalid: return "SessionInvalid";
		case NoticeKind::ProtocolMismatch: return "ProtocolMismatch";
		case NoticeKind::UnknownSemanticIds: return "UnknownSemanticIds";
		case NoticeKind::FutureLensReady: return "FutureLensReady";
		case NoticeKind::BlackBoxReady: return "BlackBoxReady";
		case NoticeKind::InfoEvent: return "InfoEvent";
		case NoticeKind::Error: return "Error";
		}
		return "?";
	}

	int port_;
	std::string name_;
	SessionMachine m_;
	WebSocket ws_;
	std::map<std::string, double> timers_;
	std::string held_;
	double heldAt_ = 0;
};

// ------------------------------------------------------------------ scenario
int g_failures = 0, g_checks = 0;
#define EXPECT(cond, what)                                                                  \
	do                                                                                      \
	{                                                                                       \
		++g_checks;                                                                         \
		if (!(cond))                                                                        \
		{                                                                                   \
			++g_failures;                                                                   \
			std::printf("    FAIL %s  (%s:%d: %s)\n", what, __FILE__, __LINE__, #cond);    \
		}                                                                                   \
		else                                                                                \
		{                                                                                   \
			std::printf("    ok   %s\n", what);                                             \
		}                                                                                   \
	} while (0)

const std::string E = "earth.command.";
const std::string LUNA01 = "earth.command.hangar.luna01";
const std::string STORAGE = "earth.command.hangar.storage";

// Waits until the mirror reaches the server snapshot's seq, then diffs them.
bool Converged(Shell& s, std::vector<std::string>& diffs, bool resources = false)
{
	for (int attempt = 0; attempt < 8; ++attempt)
	{
		const json::Value snap = s.AuthorizedGet(s.machine().credentials().sessionId.empty()
				? std::string()
				: std::string(kApiPrefix) + "/sessions/" + s.machine().credentials().sessionId + "/snapshot");
		StateMirror server;
		if (!server.LoadSnapshot(snap)) { diffs = {"snapshot unavailable"}; s.PumpFor(0.5); continue; }
		const int64_t target = server.model().lastSeq;
		s.PumpUntil([&] { return s.machine().model().lastSeq >= target && !s.machine().ledger().busy(); }, 5.0);
		s.PumpFor(0.4);  // let object refreshes triggered by the last events land
		if (s.machine().model().lastSeq != target) continue;  // the world moved on: sample again
		MirrorDiffOptions o;
		o.compareResources = resources;
		diffs = DiffMirrors(s.machine().model(), server.model(), o);
		if (diffs.empty()) return true;
	}
	return false;
}

void ExpectConverged(Shell& s, const char* what, bool resources = false)
{
	std::vector<std::string> diffs;
	const bool ok = Converged(s, diffs, resources);
	EXPECT(ok, what);
	for (size_t i = 0; i < diffs.size() && i < 12; ++i) std::printf("         diff: %s\n", diffs[i].c_str());
}

// Submits one intent and waits for its resolution. Returns the resolution detail.
std::string Act(Shell& s, const std::string& action, const std::string& target,
	std::vector<std::pair<std::string, ParamValue>> params = {}, double timeout = 20.0)
{
	SemanticIntent in;
	in.action = action;
	in.target = target;
	in.params = std::move(params);
	Effects fx;
	const size_t mark = s.log.size();
	const uint64_t id = s.machine().Submit(in, fx);
	s.Run(std::move(fx));
	std::string outcome;
	s.PumpUntil(
		[&] {
			for (size_t i = mark; i < s.log.size(); ++i)
			{
				const Notice& n = s.log[i];
				if (n.localId != id) continue;
				if (n.kind == NoticeKind::CommandResolved && n.detail != "stale") { outcome = n.detail; return true; }
				if (n.kind == NoticeKind::CommandSuperseded) { outcome = "superseded"; return true; }
				if (n.kind == NoticeKind::IntentRejected) { outcome = "rejected_locally:" + n.detail; return true; }
			}
			return false;
		},
		timeout);
	std::printf("      %-22s %-48s → %s\n", action.c_str(), target.c_str(), outcome.empty() ? "(timeout)" : outcome.c_str());
	return outcome;
}

bool ReadyState(Shell& s) { return s.machine().state() == SessionState::Ready; }

std::string ReadText(const std::string& path)
{
	std::ifstream f(path);
	std::ostringstream ss;
	ss << f.rdbuf();
	return ss.str();
}
}  // namespace

int main(int argc, char** argv)
{
	int port = 8765;
	std::string root = ".", startCmd, stopCmd;
	for (int i = 1; i + 1 < argc; i += 2)
	{
		const std::string a = argv[i];
		if (a == "--port") port = std::atoi(argv[i + 1]);
		else if (a == "--root") root = argv[i + 1];
		else if (a == "--start-cmd") startCmd = argv[i + 1];
		else if (a == "--stop-cmd") stopCmd = argv[i + 1];
	}
	SemanticRegistry registry;
	registry.Load(json::parse(ReadText(root + "/Content/Systems/SemanticIds/DT_SemanticIds_EarthCommand.json")).value);
	const double t0 = Now();

	Shell s(port, "client-1");
	std::printf("[1] startup: ready → features → create → snapshot → realtime\n");
	s.Run(s.machine().Start(Credentials()));
	EXPECT(s.PumpUntil([&] { return ReadyState(s); }, 20.0), "session ready");
	EXPECT(s.machine().model().playerLocation == E + "observation_deck", "starts on the observation deck");
	EXPECT(s.machine().model().clock.mode == "PAUSED", "clock paused until a zone is entered");
	EXPECT(registry.UnknownInSnapshot(s.machine().model()).empty(), "every snapshot id is in the semantic registry");
	ExpectConverged(s, "mirror == server snapshot after startup");

	std::printf("[2] lost command response → retry with the same Idempotency-Key → replayed answer\n");
	s.loseNextCommandResponses = 1;
	const int sentBefore = s.stats.commandsSent;
	EXPECT(Act(s, "world.zone_entered", E + "engineering") == "applied", "zone entry applied exactly once");
	EXPECT(s.stats.injectedLostResponses == 1, "one response was lost");
	EXPECT(s.stats.commandsSent - sentBefore == 2 && s.stats.replayedAnswers == 1, "second attempt answered with Idempotent-Replayed");
	EXPECT(s.machine().model().clock.mode == "REALTIME", "clock started (REALTIME)");
	ExpectConverged(s, "mirror == server after the replayed command");

	std::printf("[3] realtime frames duplicated and reordered while trusted time passes\n");
	s.scrambleRealtime = true;
	EXPECT(s.PumpUntil([&] { return s.machine().model().incident(E + "power_incident") != nullptr; }, 60.0),
		"incident.started arrives once the hidden fault happens");
	s.PumpFor(1.0);
	s.scrambleRealtime = false;
	EXPECT(s.machine().model().clock.mode == "DECISION_PAUSED", "clock DECISION_PAUSED by the incident");
	EXPECT(s.machine().sequencer().duplicatesDropped() > 0, "duplicates dropped by the sequencer");
	ExpectConverged(s, "mirror == server after scrambled delivery");
	s.PumpFor(6.0);  // the clock is paused: resource values settle after one refresh window
	ExpectConverged(s, "mirror == server including resource values (clock paused)", true);

	std::printf("[4] forced STALE_STATE → snapshot → resubmitted with new ids\n");
	s.machine().DebugForceStaleNextCommand();
	size_t mark = s.log.size();
	EXPECT(Act(s, "system.inspect", E + "engineering.power_bus_b") == "applied", "inspect applied after reconciliation");
	EXPECT(s.Saw(NoticeKind::CommandResolved, "stale", mark), "the server answered STALE_STATE first");
	ExpectConverged(s, "mirror == server after stale reconciliation");

	std::printf("[5] act on the physical system (Earth Command power incident)\n");
	EXPECT(Act(s, "world.zone_entered", E + "training") == "applied", "enter training");
	EXPECT(Act(s, "system.set_mode", E + "training.simulator", {{"mode", ParamValue::Str("off")}}) == "applied", "shed the simulator load");
	EXPECT(s.machine().model().object(E + "training.simulator") && s.machine().model().object(E + "training.simulator")->power == "off",
		"simulator power off in the mirror");
	EXPECT(Act(s, "world.zone_entered", E + "engineering") == "applied", "back to engineering");
	EXPECT(Act(s, "repair.perform", E + "engineering.power_bus_b") == "applied", "repair power bus B");
	EXPECT(Act(s, "mission.clock_set", "", {{"mode", ParamValue::Str("ACCELERATED")}}) == "applied", "clock ACCELERATED");

	std::printf("[6] Future Lens (known-only) from the live session\n");
	{
		json::Value candidates = json::Value::Array();
		json::Value c = json::Value::Object();
		c.set("id", json::Value::String("go_hangar"));
		c.set("action", json::Value::String("world.zone_entered"));
		c.set("target", json::Value::String(E + "hangar"));
		candidates.push(c);
		mark = s.log.size();
		s.Run(s.machine().RequestFutureLens(candidates, 8));
		EXPECT(s.Saw(NoticeKind::FutureLensReady, "", mark), "Future Lens answered");
		for (size_t i = mark; i < s.log.size(); ++i)
		{
			if (s.log[i].kind == NoticeKind::FutureLensReady)
			{
				const FutureLensModel lens = ParseFutureLens(s.log[i].data);
				EXPECT(lens.ok && !lens.anticipatesUnforeseeable && !lens.branches.empty(), "Future Lens parsed, known-only");
			}
		}
	}

	std::printf("[7] WebSocket dropped → HTTP restore → resume\n");
	const int reconnectsBefore = s.machine().reconnectAttempts();
	mark = s.log.size();
	s.KillSocket();
	// this shell runs HTTP synchronously, so the Recovering state is observed through the notices
	EXPECT(s.PumpUntil([&] { return s.Saw(NoticeKind::StateChanged, "Recovering", mark); }, 5.0), "recovering after the drop");
	EXPECT(s.PumpUntil([&] { return ReadyState(s) && s.Saw(NoticeKind::RestoreSummary, "", mark); }, 15.0), "ready again (HTTP restore)");
	EXPECT(s.machine().reconnectAttempts() == reconnectsBefore + 1, "one recovery");
	EXPECT(s.PumpUntil([&] { const IncidentInfo* i = s.machine().model().incident(E + "power_incident"); return i && i->resolved; }, 60.0),
		"incident resolved as trusted time passes");
	ExpectConverged(s, "mirror == server after reconnect");

	std::printf("[8] backend process restart (same database)\n");
	if (!stopCmd.empty() && !startCmd.empty())
	{
		EXPECT(std::system(stopCmd.c_str()) == 0, "backend stopped");
		s.PumpFor(4.0);
		EXPECT(s.machine().state() == SessionState::Recovering, "recovering while the backend is down");
		EXPECT(std::system(startCmd.c_str()) == 0, "backend started again");
		EXPECT(s.PumpUntil([&] { return ReadyState(s); }, 40.0), "ready after the restart");
		ExpectConverged(s, "mirror == server after the restart");
	}
	else
	{
		std::printf("    skip (no --stop-cmd/--start-cmd)\n");
	}

	std::printf("[9] LUNA-01 inspection, loadout, charging, authorization\n");
	Act(s, "world.zone_entered", E + "hangar");
	for (const char* sub : {"power", "life_support", "comms", "radiation_protection"})
	{
		Act(s, "system.inspect", LUNA01 + "." + sub);
	}
	Act(s, "system.inspect", LUNA01 + ".cargo_hold");
	EXPECT(Act(s, "module.install", LUNA01,
			   {{"slot", ParamValue::Str("radiation_protection")}, {"item", ParamValue::Str("module.radiation_shelter_liner")},
				   {"from", ParamValue::Str(STORAGE)}}) == "applied",
		"radiation shelter liner installed");
	EXPECT(Act(s, "cargo.transfer", LUNA01 + ".cargo_hold",
			   {{"item", ParamValue::Str("cargo.water_tank")}, {"quantity", ParamValue::Int(2)}, {"from", ParamValue::Str(STORAGE)}}) == "applied",
		"water loaded");
	EXPECT(Act(s, "cargo.transfer", LUNA01 + ".cargo_hold",
			   {{"item", ParamValue::Str("spare.habitat_spares_kit")}, {"quantity", ParamValue::Int(1)}, {"from", ParamValue::Str(STORAGE)}}) == "applied",
		"spares loaded");
	auto requirementsMet = [&] {
		const AuthorizationInfo& a = s.machine().model().authorization;
		if (!a.present || a.requirements.empty()) return false;
		for (const RequirementInfo& r : a.requirements) if (!r.met) return false;
		return true;
	};
	EXPECT(s.PumpUntil(requirementsMet, 240.0), "every authorization requirement met (charging in trusted time)");
	ExpectConverged(s, "mirror == server before authorization (resources lag ≤ one refresh while charging)");
	mark = s.log.size();
	const std::string auth = Act(s, "mission.authorize", LUNA01);
	EXPECT(auth == "applied" || auth == "mission_complete", "LUNA-01 launch authorized");
	EXPECT(s.PumpUntil([&] { return s.machine().model().missionId == "luna_01.the_last_light"; }, 10.0), "campaign moved to LUNA-01 (snapshot after transition)");
	EXPECT(s.machine().model().activePhase() == "LUNA_01", "active phase LUNA_01");
	EXPECT(!registry.UnknownInSnapshot(s.machine().model()).empty(), "LUNA-01 ids are outside the Earth Command registry (reported, not fatal)");
	ExpectConverged(s, "mirror == server after the campaign transition");

	std::printf("[10] Black Box of the Earth Command timeline\n");
	{
		std::string ecTimeline;
		for (const Notice& n : s.log)
		{
			if (n.kind == NoticeKind::EventApplied && n.detail == "mission.transitioned")
			{
				ecTimeline = n.data["timeline_id"].asString();  // envelope timeline = the one that ended
			}
		}
		mark = s.log.size();
		s.Run(s.machine().RequestBlackBox(ecTimeline, false));
		bool parsed = false;
		for (size_t i = mark; i < s.log.size(); ++i)
		{
			if (s.log[i].kind == NoticeKind::BlackBoxReady)
			{
				const BlackBoxModel bb = ParseBlackBox(s.log[i].data);
				parsed = bb.ok && !bb.nodes.empty() && bb.edgesResolve();
			}
		}
		EXPECT(parsed, "Black Box parsed, causal edges resolve");
	}

	std::printf("[11] second client process restores from persisted credentials\n");
	{
		Shell s2(port, "client-2");
		s2.Run(s2.machine().Start(s.machine().credentials()));
		EXPECT(s2.PumpUntil([&] { return ReadyState(s2); }, 20.0), "restored and ready");
		EXPECT(!s2.Saw(NoticeKind::SessionReplaced), "the same campaign (not replaced)");
		s.PumpFor(0.5);
		std::vector<std::string> diffs = DiffMirrors(s2.machine().model(), s.machine().model());
		EXPECT(diffs.empty() || s2.machine().model().lastSeq != s.machine().model().lastSeq, "both clients see the same state");
		for (size_t i = 0; i < diffs.size() && i < 8; ++i) std::printf("         diff: %s\n", diffs[i].c_str());
		s2.Run(s2.machine().Shutdown());
	}

	std::printf("\nrequests: %d HTTP (%d × 429), %d command sends, %d replayed, %d WS connects, %d frames in\n",
		s.stats.http, s.stats.http429, s.stats.commandsSent, s.stats.replayedAnswers, s.stats.wsConnects, s.stats.wsFramesIn);
	std::printf("injected: %d lost responses, %d swaps, %d duplicate frames; sequencer dropped %d duplicates\n",
		s.stats.injectedLostResponses, s.stats.injectedSwaps, s.stats.injectedDuplicates, static_cast<int>(s.machine().sequencer().duplicatesDropped()));
	const double minutes = (Now() - t0) / 60.0;
	std::printf("elapsed %.1f min, %.1f HTTP requests/min (backend default limit 120/min)\n", minutes, s.stats.http / std::max(minutes, 1e-6));
	EXPECT(s.stats.http429 == 0, "never rate limited by the backend");
	s.Run(s.machine().Shutdown());
	std::printf("\n%s: %d/%d checks passed\n", g_failures ? "LIVE HARNESS FAILED" : "LIVE HARNESS PASSED", g_checks - g_failures, g_checks);
	return g_failures ? 1 : 0;
}
