












#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"

#include "OdysseyDebugSubsystem.generated.h"

class APlayerController;
class IConsoleObject;
class UCanvas;

UCLASS()
class ODYSSEYDEBUG_API UOdysseyDebugSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

private:
	
	UFUNCTION() void HandleVerified(int32 Count, const FString& First);
#if !UE_BUILD_SHIPPING
	void Draw(UCanvas* Canvas, APlayerController* PC);
	FDelegateHandle DrawHandle;
	TArray<IConsoleObject*> Commands;
	FString LastVerify;
#endif
	bool bOverlay = true;
};
