// ODYSSEY protocol core — minimal JSON value, parser and writer.
//
// Engine-independent C++17 (no exceptions, no RTTI, no engine types) so the whole odyssey.game.v1
// client logic compiles and is tested outside Unreal (Tools/ProtocolCore) with the exact
// constraints Unreal modules build with (-fno-exceptions -fno-rtti -Wshadow -Werror). Inside
// Unreal the same code runs unchanged; OdysseyAPI converts FString <-> UTF-8 at the boundary.
//
// Scope: RFC 8259 JSON. Objects keep insertion order (stable, diff-friendly serialization).
// Numbers keep an exact int64 when the literal is integral and fits; otherwise double.
#pragma once

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace odyssey::json
{

enum class Type : uint8_t
{
	Null,
	Bool,
	Number,
	String,
	Array,
	Object
};

class Value
{
public:
	using Member = std::pair<std::string, Value>;

	Value() = default;
	static Value Null() { return Value(); }
	static Value Bool(bool b)
	{
		Value v;
		v.type_ = Type::Bool;
		v.bool_ = b;
		return v;
	}
	static Value Int(int64_t i)
	{
		Value v;
		v.type_ = Type::Number;
		v.int_ = i;
		v.num_ = static_cast<double>(i);
		v.isInt_ = true;
		return v;
	}
	static Value Number(double d)
	{
		Value v;
		v.type_ = Type::Number;
		v.num_ = d;
		v.isInt_ = false;
		return v;
	}
	static Value String(std::string s)
	{
		Value v;
		v.type_ = Type::String;
		v.str_ = std::move(s);
		return v;
	}
	static Value Array() { Value v; v.type_ = Type::Array; return v; }
	static Value Object() { Value v; v.type_ = Type::Object; return v; }

	Type type() const { return type_; }
	bool isNull() const { return type_ == Type::Null; }
	bool isBool() const { return type_ == Type::Bool; }
	bool isNumber() const { return type_ == Type::Number; }
	bool isInt() const { return type_ == Type::Number && isInt_; }
	bool isString() const { return type_ == Type::String; }
	bool isArray() const { return type_ == Type::Array; }
	bool isObject() const { return type_ == Type::Object; }

	bool asBool(bool fallback = false) const { return isBool() ? bool_ : fallback; }
	int64_t asInt(int64_t fallback = 0) const
	{
		if (!isNumber())
		{
			return fallback;
		}
		return isInt_ ? int_ : static_cast<int64_t>(num_);
	}
	double asDouble(double fallback = 0.0) const { return isNumber() ? num_ : fallback; }
	const std::string& asString() const
	{
		static const std::string empty;
		return isString() ? str_ : empty;
	}
	std::string stringOr(const std::string& fallback) const { return isString() ? str_ : fallback; }

	// ---- arrays
	const std::vector<Value>& items() const
	{
		static const std::vector<Value> empty;
		return isArray() ? arr_ : empty;
	}
	std::vector<Value>& mutableItems() { return arr_; }
	Value& push(Value v)
	{
		arr_.push_back(std::move(v));
		return arr_.back();
	}
	size_t size() const { return isArray() ? arr_.size() : (isObject() ? obj_.size() : 0); }

	// ---- objects
	const std::vector<Member>& members() const
	{
		static const std::vector<Member> empty;
		return isObject() ? obj_ : empty;
	}
	const Value* find(const std::string& key) const
	{
		if (!isObject())
		{
			return nullptr;
		}
		for (const Member& m : obj_)
		{
			if (m.first == key)
			{
				return &m.second;
			}
		}
		return nullptr;
	}
	bool has(const std::string& key) const { return find(key) != nullptr; }
	// Missing keys yield a shared null value, so chained lookups never crash.
	const Value& operator[](const std::string& key) const
	{
		static const Value null;
		const Value* v = find(key);
		return v ? *v : null;
	}
	// Insert or replace (keeps the original position when replacing).
	Value& set(const std::string& key, Value v)
	{
		for (Member& m : obj_)
		{
			if (m.first == key)
			{
				m.second = std::move(v);
				return m.second;
			}
		}
		obj_.emplace_back(key, std::move(v));
		return obj_.back().second;
	}
	bool erase(const std::string& key)
	{
		for (auto it = obj_.begin(); it != obj_.end(); ++it)
		{
			if (it->first == key)
			{
				obj_.erase(it);
				return true;
			}
		}
		return false;
	}

	bool operator==(const Value& o) const
	{
		if (type_ != o.type_)
		{
			return false;
		}
		switch (type_)
		{
		case Type::Null:
			return true;
		case Type::Bool:
			return bool_ == o.bool_;
		case Type::Number:
			return (isInt_ && o.isInt_) ? int_ == o.int_ : num_ == o.num_;
		case Type::String:
			return str_ == o.str_;
		case Type::Array:
			return arr_ == o.arr_;
		case Type::Object:
		{
			// order-insensitive object equality (server JSONB may reorder keys)
			if (obj_.size() != o.obj_.size())
			{
				return false;
			}
			for (const Member& m : obj_)
			{
				const Value* other = o.find(m.first);
				if (!other || !(*other == m.second))
				{
					return false;
				}
			}
			return true;
		}
		}
		return false;
	}
	bool operator!=(const Value& o) const { return !(*this == o); }

private:
	Type type_ = Type::Null;
	bool bool_ = false;
	bool isInt_ = false;
	int64_t int_ = 0;
	double num_ = 0.0;
	std::string str_;
	std::vector<Value> arr_;
	std::vector<Member> obj_;
};

struct ParseResult
{
	bool ok = false;
	Value value;
	std::string error;  // "message at byte N"
};

namespace detail
{
class Parser
{
public:
	Parser(const char* data, size_t len) : p_(data), begin_(data), end_(data + len) {}

	ParseResult run()
	{
		ParseResult r;
		ws();
		if (!parseValue(r.value, 0))
		{
			r.error = err_ + " at byte " + std::to_string(static_cast<long long>(p_ - begin_));
			return r;
		}
		ws();
		if (p_ != end_)
		{
			r.error = "trailing characters at byte " + std::to_string(static_cast<long long>(p_ - begin_));
			return r;
		}
		r.ok = true;
		return r;
	}

private:
	static constexpr int kMaxDepth = 128;
	const char* p_;
	const char* begin_;
	const char* end_;
	std::string err_;

	bool fail(const char* msg)
	{
		err_ = msg;
		return false;
	}
	void ws()
	{
		while (p_ < end_ && (*p_ == ' ' || *p_ == '\t' || *p_ == '\n' || *p_ == '\r'))
		{
			++p_;
		}
	}
	bool literal(const char* word)
	{
		size_t n = std::strlen(word);
		if (static_cast<size_t>(end_ - p_) < n || std::memcmp(p_, word, n) != 0)
		{
			return fail("invalid literal");
		}
		p_ += n;
		return true;
	}
	bool parseValue(Value& out, int depth)
	{
		if (depth > kMaxDepth)
		{
			return fail("nesting too deep");
		}
		if (p_ >= end_)
		{
			return fail("unexpected end of input");
		}
		switch (*p_)
		{
		case 'n':
			out = Value::Null();
			return literal("null");
		case 't':
			out = Value::Bool(true);
			return literal("true");
		case 'f':
			out = Value::Bool(false);
			return literal("false");
		case '"':
		{
			std::string s;
			if (!parseString(s))
			{
				return false;
			}
			out = Value::String(std::move(s));
			return true;
		}
		case '[':
			return parseArray(out, depth);
		case '{':
			return parseObject(out, depth);
		default:
			return parseNumber(out);
		}
	}
	bool parseArray(Value& out, int depth)
	{
		++p_;
		out = Value::Array();
		ws();
		if (p_ < end_ && *p_ == ']')
		{
			++p_;
			return true;
		}
		while (true)
		{
			Value item;
			ws();
			if (!parseValue(item, depth + 1))
			{
				return false;
			}
			out.push(std::move(item));
			ws();
			if (p_ >= end_)
			{
				return fail("unterminated array");
			}
			if (*p_ == ',')
			{
				++p_;
				continue;
			}
			if (*p_ == ']')
			{
				++p_;
				return true;
			}
			return fail("expected ',' or ']'");
		}
	}
	bool parseObject(Value& out, int depth)
	{
		++p_;
		out = Value::Object();
		ws();
		if (p_ < end_ && *p_ == '}')
		{
			++p_;
			return true;
		}
		while (true)
		{
			ws();
			if (p_ >= end_ || *p_ != '"')
			{
				return fail("expected object key");
			}
			std::string key;
			if (!parseString(key))
			{
				return false;
			}
			ws();
			if (p_ >= end_ || *p_ != ':')
			{
				return fail("expected ':'");
			}
			++p_;
			ws();
			Value v;
			if (!parseValue(v, depth + 1))
			{
				return false;
			}
			out.set(key, std::move(v));
			ws();
			if (p_ >= end_)
			{
				return fail("unterminated object");
			}
			if (*p_ == ',')
			{
				++p_;
				continue;
			}
			if (*p_ == '}')
			{
				++p_;
				return true;
			}
			return fail("expected ',' or '}'");
		}
	}
	static void appendUtf8(std::string& s, uint32_t cp)
	{
		if (cp < 0x80)
		{
			s += static_cast<char>(cp);
		}
		else if (cp < 0x800)
		{
			s += static_cast<char>(0xC0 | (cp >> 6));
			s += static_cast<char>(0x80 | (cp & 0x3F));
		}
		else if (cp < 0x10000)
		{
			s += static_cast<char>(0xE0 | (cp >> 12));
			s += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
			s += static_cast<char>(0x80 | (cp & 0x3F));
		}
		else
		{
			s += static_cast<char>(0xF0 | (cp >> 18));
			s += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
			s += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
			s += static_cast<char>(0x80 | (cp & 0x3F));
		}
	}
	bool hex4(uint32_t& out)
	{
		if (end_ - p_ < 4)
		{
			return fail("truncated \\u escape");
		}
		out = 0;
		for (int i = 0; i < 4; ++i)
		{
			char c = *p_++;
			out <<= 4;
			if (c >= '0' && c <= '9')
			{
				out |= static_cast<uint32_t>(c - '0');
			}
			else if (c >= 'a' && c <= 'f')
			{
				out |= static_cast<uint32_t>(c - 'a' + 10);
			}
			else if (c >= 'A' && c <= 'F')
			{
				out |= static_cast<uint32_t>(c - 'A' + 10);
			}
			else
			{
				return fail("invalid \\u escape");
			}
		}
		return true;
	}
	bool parseString(std::string& out)
	{
		++p_;  // opening quote
		while (p_ < end_)
		{
			char c = *p_++;
			if (c == '"')
			{
				return true;
			}
			if (static_cast<unsigned char>(c) < 0x20)
			{
				return fail("control character in string");
			}
			if (c != '\\')
			{
				out += c;
				continue;
			}
			if (p_ >= end_)
			{
				return fail("truncated escape");
			}
			char e = *p_++;
			switch (e)
			{
			case '"': out += '"'; break;
			case '\\': out += '\\'; break;
			case '/': out += '/'; break;
			case 'b': out += '\b'; break;
			case 'f': out += '\f'; break;
			case 'n': out += '\n'; break;
			case 'r': out += '\r'; break;
			case 't': out += '\t'; break;
			case 'u':
			{
				uint32_t cp = 0;
				if (!hex4(cp))
				{
					return false;
				}
				if (cp >= 0xD800 && cp <= 0xDBFF)
				{
					if (end_ - p_ < 6 || p_[0] != '\\' || p_[1] != 'u')
					{
						return fail("unpaired surrogate");
					}
					p_ += 2;
					uint32_t lo = 0;
					if (!hex4(lo))
					{
						return false;
					}
					if (lo < 0xDC00 || lo > 0xDFFF)
					{
						return fail("invalid low surrogate");
					}
					cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
				}
				else if (cp >= 0xDC00 && cp <= 0xDFFF)
				{
					return fail("unpaired surrogate");
				}
				appendUtf8(out, cp);
				break;
			}
			default:
				return fail("invalid escape");
			}
		}
		return fail("unterminated string");
	}
	bool parseNumber(Value& out)
	{
		const char* start = p_;
		bool integral = true;
		if (p_ < end_ && *p_ == '-')
		{
			++p_;
		}
		if (p_ >= end_ || !(*p_ >= '0' && *p_ <= '9'))
		{
			return fail("invalid value");
		}
		if (*p_ == '0')
		{
			++p_;
		}
		else
		{
			while (p_ < end_ && *p_ >= '0' && *p_ <= '9')
			{
				++p_;
			}
		}
		if (p_ < end_ && *p_ == '.')
		{
			integral = false;
			++p_;
			if (p_ >= end_ || !(*p_ >= '0' && *p_ <= '9'))
			{
				return fail("invalid fraction");
			}
			while (p_ < end_ && *p_ >= '0' && *p_ <= '9')
			{
				++p_;
			}
		}
		if (p_ < end_ && (*p_ == 'e' || *p_ == 'E'))
		{
			integral = false;
			++p_;
			if (p_ < end_ && (*p_ == '+' || *p_ == '-'))
			{
				++p_;
			}
			if (p_ >= end_ || !(*p_ >= '0' && *p_ <= '9'))
			{
				return fail("invalid exponent");
			}
			while (p_ < end_ && *p_ >= '0' && *p_ <= '9')
			{
				++p_;
			}
		}
		std::string text(start, static_cast<size_t>(p_ - start));
		if (integral && text.size() <= 18)
		{
			out = Value::Int(std::strtoll(text.c_str(), nullptr, 10));
		}
		else
		{
			out = Value::Number(std::strtod(text.c_str(), nullptr));
		}
		return true;
	}
};

inline void writeString(std::string& out, const std::string& s)
{
	out += '"';
	for (unsigned char c : s)
	{
		switch (c)
		{
		case '"': out += "\\\""; break;
		case '\\': out += "\\\\"; break;
		case '\b': out += "\\b"; break;
		case '\f': out += "\\f"; break;
		case '\n': out += "\\n"; break;
		case '\r': out += "\\r"; break;
		case '\t': out += "\\t"; break;
		default:
			if (c < 0x20)
			{
				char buf[8];
				std::snprintf(buf, sizeof(buf), "\\u%04x", c);
				out += buf;
			}
			else
			{
				out += static_cast<char>(c);
			}
		}
	}
	out += '"';
}

inline void writeValue(std::string& out, const Value& v)
{
	switch (v.type())
	{
	case Type::Null:
		out += "null";
		break;
	case Type::Bool:
		out += v.asBool() ? "true" : "false";
		break;
	case Type::Number:
	{
		if (v.isInt())
		{
			out += std::to_string(static_cast<long long>(v.asInt()));
		}
		else if (!std::isfinite(v.asDouble()))
		{
			out += "null";  // JSON has no NaN/Inf
		}
		else
		{
			char buf[32];
			std::snprintf(buf, sizeof(buf), "%.17g", v.asDouble());
			out += buf;
		}
		break;
	}
	case Type::String:
		writeString(out, v.asString());
		break;
	case Type::Array:
	{
		out += '[';
		bool first = true;
		for (const Value& item : v.items())
		{
			if (!first)
			{
				out += ',';
			}
			first = false;
			writeValue(out, item);
		}
		out += ']';
		break;
	}
	case Type::Object:
	{
		out += '{';
		bool first = true;
		for (const Value::Member& m : v.members())
		{
			if (!first)
			{
				out += ',';
			}
			first = false;
			writeString(out, m.first);
			out += ':';
			writeValue(out, m.second);
		}
		out += '}';
		break;
	}
	}
}
}  // namespace detail

inline ParseResult parse(const std::string& text)
{
	return detail::Parser(text.data(), text.size()).run();
}

inline std::string write(const Value& v)
{
	std::string out;
	detail::writeValue(out, v);
	return out;
}

}  // namespace odyssey::json
