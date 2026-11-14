// Test-only probe: records every command resolution the backend subsystem reports, so the
// Engineering slice test can check which semantic action a console control actually sent.
#pragma once

#include "CoreMinimal.h"
#include "OdysseyBackendTypes.h"
#include "UObject/Object.h"

#include "OdysseySliceTestProbe.generated.h"

UCLASS(Transient)
class UOdysseySliceTestProbe : public UObject
{
	GENERATED_BODY()

public:
	UFUNCTION()
	void HandleResolved(const FOdysseyCommandResolution& Resolution) { Resolutions.Add(Resolution); }

	const FOdysseyCommandResolution* Find(int64 LocalId) const
	{
		return Resolutions.FindByPredicate([LocalId](const FOdysseyCommandResolution& R) { return R.LocalId == LocalId; });
	}

	TArray<FOdysseyCommandResolution> Resolutions;
};
