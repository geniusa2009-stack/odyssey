#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "OdysseyMobileControls.generated.h"

class UButton;
class UTextBlock;

// Captures one touch per surface; movement and look have independent pointer ownership.
UCLASS()
class ODYSSEYUI_API UOdysseyTouchSurface : public UUserWidget
{
	GENERATED_BODY()
public:
	bool bMovement = false;
	TFunction<void(FVector2D)> OnAxis;
protected:
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	virtual FReply NativeOnTouchStarted(const FGeometry&, const FPointerEvent&) override;
	virtual FReply NativeOnTouchMoved(const FGeometry&, const FPointerEvent&) override;
	virtual FReply NativeOnTouchEnded(const FGeometry&, const FPointerEvent&) override;
	virtual void NativeOnMouseCaptureLost(const FCaptureLostEvent&) override;
	virtual void NativeTick(const FGeometry&, float) override;
	virtual int32 NativePaint(const FPaintArgs&, const FGeometry&, const FSlateRect&,
		FSlateWindowElementList&, int32, const FWidgetStyle&, bool) const override;
private:
	FDelegateHandle BackgroundHandle;
	int32 Finger = INDEX_NONE;
	FVector2D Origin = FVector2D::ZeroVector;
	FVector2D Last = FVector2D::ZeroVector;
	FVector2D Axis = FVector2D::ZeroVector;
	void ResetTouch();
};

// Created only by Android controllers. USafeZone handles display cutouts and system insets.
UCLASS()
class ODYSSEYUI_API UOdysseyMobileControls : public UUserWidget
{
	GENERATED_BODY()
public:
	bool bStation = false;
	TFunction<void(FVector2D)> OnMove;
	TFunction<void(FVector2D)> OnLook;
	TFunction<void(int32)> OnAction;
	void SetAction(int32 Index, const FString& Label, bool bEnabled = true);
	void SetHeading(const FString& Heading, const FString& Detail);
protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
private:
	UPROPERTY(Transient) TArray<TObjectPtr<UButton>> Buttons;
	UPROPERTY(Transient) TArray<TObjectPtr<UTextBlock>> Labels;
	UPROPERTY(Transient) TObjectPtr<UTextBlock> HeadingText;
	UPROPERTY(Transient) TObjectPtr<UTextBlock> DetailText;
	UFUNCTION() void Action0();
	UFUNCTION() void Action1();
	UFUNCTION() void Action2();
	UFUNCTION() void Action3();
	UFUNCTION() void Action4();
	UFUNCTION() void Action5();
	UFUNCTION() void Action6();
	UFUNCTION() void Action7();
};
