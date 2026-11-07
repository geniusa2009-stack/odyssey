


#pragma once

#include "CoreMinimal.h"
#include "Containers/StringConv.h"

#include <string>

namespace OdysseyConv
{
inline FString ToFString(const std::string& S)
{
	const FUTF8ToTCHAR Conv(S.data(), static_cast<int32>(S.size()));
	return FString(Conv.Length(), Conv.Get());
}

inline FName ToFName(const std::string& S)
{
	return S.empty() ? NAME_None : FName(*ToFString(S));
}

inline std::string ToStd(const FString& S)
{
	const FTCHARToUTF8 Conv(*S, S.Len());
	return std::string(Conv.Get(), static_cast<size_t>(Conv.Length()));
}

inline std::string ToStd(const FName& N)
{
	return N.IsNone() ? std::string() : ToStd(N.ToString());
}
}  
