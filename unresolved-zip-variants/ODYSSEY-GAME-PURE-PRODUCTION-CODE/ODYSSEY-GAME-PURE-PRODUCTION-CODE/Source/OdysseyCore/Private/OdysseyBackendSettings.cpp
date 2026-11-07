
#include "OdysseyBackendSettings.h"

#include "HAL/PlatformMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

FName UOdysseyBackendSettings::GetActiveEnvironmentName() const
{
	FString FromCommandLine;
	if (FParse::Value(FCommandLine::Get(), TEXT("OdysseyEnv="), FromCommandLine) && !FromCommandLine.IsEmpty())
	{
		return FName(*FromCommandLine);
	}
	const FString FromEnvironment = FPlatformMisc::GetEnvironmentVariable(TEXT("ODYSSEY_ENV"));
	if (!FromEnvironment.IsEmpty())
	{
		return FName(*FromEnvironment);
	}
	return DefaultEnvironment;
}

bool UOdysseyBackendSettings::ResolveActiveEnvironment(FOdysseyBackendEnvironment& Out, FString& Error) const
{
	const FName Name = GetActiveEnvironmentName();
	const FOdysseyBackendEnvironment* Env = Environments.Find(Name);
	if (!Env)
	{
		Error = FString::Printf(TEXT("ODYSSEY backend environment '%s' is not configured"), *Name.ToString());
		return false;
	}
	const bool bSecure = Env->ServerRoot.StartsWith(TEXT("https://"));
	if (!bSecure && !Env->bAllowInsecureTransport)
	{
		Error = FString::Printf(TEXT("environment '%s' uses plain http but bAllowInsecureTransport is false"), *Name.ToString());
		return false;
	}
#if UE_BUILD_SHIPPING
	if (!bSecure)
	{
		Error = TEXT("Shipping builds require https/wss");
		return false;
	}
#endif
	Out = *Env;
	Out.ServerRoot.RemoveFromEnd(TEXT("/"));
	return true;
}
