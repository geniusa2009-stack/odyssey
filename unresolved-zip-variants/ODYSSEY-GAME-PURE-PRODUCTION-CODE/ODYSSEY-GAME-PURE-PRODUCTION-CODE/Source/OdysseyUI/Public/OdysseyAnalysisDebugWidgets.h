



#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "OdysseyBackendTypes.h"

#include "OdysseyAnalysisDebugWidgets.generated.h"

class UTextBlock;

UCLASS()
class ODYSSEYUI_API UOdysseyFutureLensDebugWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "Odyssey|FutureLens") void ShowLens(const FOdysseyFutureLensView& View);
	static FString Describe(const FOdysseyFutureLensView& View);

protected:
	UPROPERTY(meta = (BindWidgetOptional)) TObjectPtr<UTextBlock> Body;
	virtual void NativeConstruct() override;
};

UCLASS()
class ODYSSEYUI_API UOdysseyBlackBoxDebugWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "Odyssey|BlackBox") void ShowBlackBox(const FOdysseyBlackBoxView& View);

protected:
	UPROPERTY(meta = (BindWidgetOptional)) TObjectPtr<UTextBlock> Header;
	virtual void NativeConstruct() override;
	virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;

private:
	FOdysseyBlackBoxView Graph;
};
