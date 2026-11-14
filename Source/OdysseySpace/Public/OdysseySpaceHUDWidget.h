// Code-drawn front-end / navigation HUD for the space experience: brand badge, main menu,
// transfer planner (Earth / Moon / Mars), transfer telemetry, arrival banner and fades.
// Restrained ODYSSEY styling: graphite panels, white type, ion-blue accents only where meaningful.
#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"

#include "OdysseySpaceHUDWidget.generated.h"

class AOdysseySpacePlayerController;

UCLASS()
class ODYSSEYSPACE_API UOdysseySpaceHUDWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(Transient) TObjectPtr<AOdysseySpacePlayerController> Owner;

	// Touch hit tests matching the painted layout (local slate units of the full-viewport HUD).
	static int32 HitMenuItem(FVector2f P, FVector2f Screen);
	static int32 HitPlannerRow(FVector2f P, FVector2f Screen, int32 NumBodies);

protected:
	virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
};
