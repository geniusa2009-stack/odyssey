// Animated ODYSSEY logo (code-drawn, resolution independent). Usable as the startup reveal
// (Intro: black open, scan line, diamond mark draws on, wordmark strokes draw on with tracking
// settling, ion light sweep, subtitle typewriter, fade to scene) and as a short Sting overlay for
// loading / menu / trailer cuts. Real time based, so it plays the same under pause or dilation.
#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"

#include "OdysseyLogoWidget.generated.h"

UENUM(BlueprintType)
enum class EOdysseyLogoStyle : uint8
{
	Intro,
	Sting
};

UCLASS()
class ODYSSEYSPACE_API UOdysseyLogoWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Logo") FString Subtitle = TEXT("EARTH COMMAND  /  DEEP SPACE PROGRAM");

	UFUNCTION(BlueprintCallable, Category = "Odyssey|Logo") void Play(EOdysseyLogoStyle InStyle);
	// Jump to the outro (keeps the fade so a skip never pops).
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Logo") void Skip();
	UFUNCTION(BlueprintPure, Category = "Odyssey|Logo") float GetElapsed() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|Logo") float GetDuration() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|Logo") bool IsFinished() const { return bPlayed && GetElapsed() >= GetDuration(); }
	// 0..1: how much of the scene is visible behind the intro's black open.
	UFUNCTION(BlueprintPure, Category = "Odyssey|Logo") float GetSceneReveal() const;
	// Before Play(): paint solid black (used while shaders warm up so the scene never pops in).
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Logo") bool bHoldBlack = true;

protected:
	virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;

private:
	EOdysseyLogoStyle Style = EOdysseyLogoStyle::Intro;
	double StartTime = 0.0;
	double TimeOffset = 0.0;
	bool bPlayed = false;
};
