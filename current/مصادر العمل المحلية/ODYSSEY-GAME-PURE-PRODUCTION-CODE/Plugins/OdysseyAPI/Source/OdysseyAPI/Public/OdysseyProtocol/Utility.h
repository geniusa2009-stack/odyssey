#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <functional>
#include <iterator>
#include <type_traits>
#include <utility>

namespace odyssey::detail
{

template <class Range, class Predicate>
constexpr auto FindPtr(Range& range, Predicate&& predicate)
{
	auto it = std::find_if(std::begin(range), std::end(range), std::forward<Predicate>(predicate));
	using Element = std::remove_reference_t<decltype(*std::begin(range))>;
	using Pointer = std::add_pointer_t<Element>;
	return it == std::end(range) ? Pointer{} : std::addressof(*it);
}

template <class Range, class Predicate>
constexpr auto FindPtr(const Range& range, Predicate&& predicate)
{
	auto it = std::find_if(std::begin(range), std::end(range), std::forward<Predicate>(predicate));
	using Element = std::remove_reference_t<decltype(*std::begin(range))>;
	using Pointer = std::add_pointer_t<std::add_const_t<Element>>;
	return it == std::end(range) ? Pointer{} : std::addressof(*it);
}

template <class Range, class Key>
constexpr auto FindById(Range& range, const Key& id)
{
	return FindPtr(range, [&](const auto& value) { return value.id == id; });
}

template <class Range, class Key>
constexpr auto FindById(const Range& range, const Key& id)
{
	return FindPtr(range, [&](const auto& value) { return value.id == id; });
}

template <class Range, class Predicate>
constexpr bool Any(const Range& range, Predicate&& predicate)
{
	return std::any_of(std::begin(range), std::end(range), std::forward<Predicate>(predicate));
}

template <class Range, class Predicate>
constexpr bool All(const Range& range, Predicate&& predicate)
{
	return std::all_of(std::begin(range), std::end(range), std::forward<Predicate>(predicate));
}

template <class Table, class Key>
constexpr auto Lookup(const Table& table, const Key& key)
{
	using Result = const typename Table::value_type::second_type*;
	const auto* entry = FindPtr(table, [&](const auto& pair) { return pair.first == key; });
	return entry ? std::addressof(entry->second) : Result{};
}

}
