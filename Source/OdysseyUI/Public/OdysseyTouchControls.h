// On-screen touch controls for phones/tablets (shown only on touch platforms, or with -OdysseyTouch on
// desktop for testing). Painted natively in the ODYSSEY aerospace style: a floating movement stick on
// the left, drag-to-look on the right, and labelled context buttons. Owners (the space and station
// player controllers) configure the buttons and read the stick / look values; button presses and free
// taps are delivered through native delegates. Layout unit = screen height, so it is resolution- and
// DPI-independent; everything stays inside the safe area.
#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"

#include "OdysseyTouchControls.generated.h"

struct FOdysseyTouchButton
{
	FName Id;
	FString Label;
	FVector2f Anchor = FVector2f(1.f, 1.f);  // 0..1 of the safe area (1,1 = bottom right)
	FVector2f Offset = FVector2f::ZeroVector;  // button centre from the anchor, in screen heights
	float Radius = 0.07f;                      // in screen heights
	bool bPrimary = false;                     // ion-filled (main action)
	bool bVisible = true;
};

DECLARE_DELEGATE_OneParam(FOdysseyTouchPressed, FName /*ButtonId*/);
// Free tap (not on a button / stick / look area). Position in local slate units; returns true if used.
DECLARE_DELEGATE_RetVal_TwoParams(bool, FOdysseyTouchTap, FVector2f /*Pos*/, FVector2f /*ScreenSize*/);

UCLASS()
class ODYSSEYUI_API UOdysseyTouchControls : public UUserWidget
{
	GENERATED_BODY()

public:
	// True on touch platforms (Android / iOS) or when -OdysseyTouch is on the command line.
	static bool ShouldUseTouch();

	void SetButtons(const TArray<FOdysseyTouchButton>& InButtons);
	void SetButtonVisible(FName Id, bool bVisible);
	void SetButtonLabel(FName Id, const FString& Label);
	void SetStickEnabled(bool bEnabled);
	void SetLookEnabled(bool bEnabled) { bLook = bEnabled; }
	// Optional status chip (top centre) and context prompt (above the action buttons).
	void SetStatus(const FString& InStatus, const FString& InPrompt) { Status = InStatus; Prompt = InPrompt; }

	// Movement stick, x right / y forward, length 0..1.
	FVector2D GetMove() const { return Move; }
	// Look delta accumulated since the last call (x yaw right, y pitch down), in controller input units.
	FVector2D ConsumeLook();

	FOdysseyTouchPressed OnPressed;
	FOdysseyTouchTap OnTap;

	float LookSensitivity = 0.11f;

protected:
	virtual void NativeConstruct() override;
	virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FReply NativeOnTouchStarted(const FGeometry& Geo, const FPointerEvent& Event) override;
	virtual FReply NativeOnTouchMoved(const FGeometry& Geo, const FPointerEvent& Event) override;
	virtual FReply NativeOnTouchEnded(const FGeometry& Geo, const FPointerEvent& Event) override;
	virtual FReply NativeOnMouseButtonDown(const FGeometry& Geo, const FPointerEvent& Event) override;
	virtual FReply NativeOnMouseMove(const FGeometry& Geo, const FPointerEvent& Event) override;
	virtual FReply NativeOnMouseButtonUp(const FGeometry& Geo, const FPointerEvent& Event) override;

private:
	enum class EKind : uint8 { Stick, Look, Button, Tap };
	struct FFinger
	{
		EKind Kind = EKind::Tap;
		FVector2f Start = FVector2f::ZeroVector;
		FVector2f Last = FVector2f::ZeroVector;
		FName Button;
	};

	FReply Begin(uint32 Pointer, const FGeometry& Geo, const FPointerEvent& Event);
	FReply Update(uint32 Pointer, const FGeometry& Geo, const FPointerEvent& Event);
	FReply End(uint32 Pointer, const FGeometry& Geo, const FPointerEvent& Event);

	// Safe-area rectangle (local units) and layout unit.
	void Layout(const FVector2f& Size, FVector2f& OutMin, FVector2f& OutMax, float& OutS) const;
	FVector2f ButtonCentre(const FOdysseyTouchButton& B, const FVector2f& Min, const FVector2f& Max, float S) const;
	const FOdysseyTouchButton* HitButton(const FVector2f& P, const FVector2f& Size) const;
	bool InStickZone(const FVector2f& P, const FVector2f& Size) const;

	TArray<FOdysseyTouchButton> Buttons;
	TMap<uint32, FFinger> Fingers;
	FVector2D Move = FVector2D::ZeroVector;
	FVector2D LookAccum = FVector2D::ZeroVector;
	FVector2f StickCentre = FVector2f::ZeroVector;
	FVector2f StickKnob = FVector2f::ZeroVector;
	bool bStickActive = false;
	FString Status;
	FString Prompt;
	bool bStick = false;
	bool bLook = false;
	mutable FVector2f LastSize = FVector2f(1920.f, 1080.f);
};
