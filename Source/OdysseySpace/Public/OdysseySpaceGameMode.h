// Front end + solar transit flow of ODYSSEY:
//   Intro (animated logo) -> Menu (Earth hero shot) -> Navigation (orbit, choose Earth / Moon / Mars,
//   launch transfers) -> Descend to Earth Command (opens the Earth Command station map).
// Keyboard: Up/Down or W/S menu, Enter/Space confirm, Esc back, Left/Right or A/D or 1-3 destination,
// C camera, E descend (at Earth). Gamepad: d-pad / face buttons equivalents.
// -OdysseyCapture on the command line runs a scripted tour that writes validation screenshots to
// Saved/Odyssey/SpaceCapture and quits; -OdysseySkipIntro starts at the menu.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"

#include "OdysseySpaceGameMode.generated.h"

class AOdysseyTransitDirector;
class UOdysseyLogoWidget;
class UOdysseySpaceHUDWidget;

UENUM(BlueprintType)
enum class EOdysseySpaceFlow : uint8
{
	Intro,
	Menu,
	Navigation,
	Descending
};

UCLASS()
class ODYSSEYSPACE_API AOdysseySpaceGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AOdysseySpaceGameMode();
};

UCLASS(Config = Game)
class ODYSSEYSPACE_API AOdysseySpacePlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AOdysseySpacePlayerController();

	// Map opened by "Begin Mission" / "Descend to Earth Command".
	UPROPERTY(Config, EditAnywhere, Category = "Odyssey|Space") FString EarthCommandMap = TEXT("/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice");

	UFUNCTION(BlueprintPure, Category = "Odyssey|Space") EOdysseySpaceFlow GetFlow() const { return Flow; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Space") int32 GetMenuIndex() const { return MenuIndex; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Space") int32 GetSelectedBody() const { return SelectedBody; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Space") float GetFlowTime() const { return FlowTime; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Space") float GetFadeToBlack() const;
	AOdysseyTransitDirector* GetDirector() const { return Director; }
	UOdysseyLogoWidget* GetLogo() const { return Logo; }

	static constexpr int32 NumMenuItems = 3;
	static FText MenuLabel(int32 Index);
	static FText MenuDetail(int32 Index);

	// Flow actions (input handlers; public for tests and the capture tour).
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void SkipIntro();
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void MenuMove(int32 Delta);
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void Confirm();
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void Back();
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void SelectBody(int32 Index);
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void CycleCamera();
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void Descend();
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void EnterNavigation();

	// Exec: "OdysseyTravel 2" launches a transfer to body 2.
	UFUNCTION(Exec) void OdysseyTravel(int32 Index);

	// Scalability preset (0 low .. 3 epic), cycled with Q in the menu / navigation.
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Space") void CycleQuality();
	FString GetQualityName() const;

protected:
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	virtual void PlayerTick(float DeltaTime) override;

private:
	void SetFlow(EOdysseySpaceFlow NewFlow);
	void UpdateMobileControls();
	float MobileUpdateTime = 0.f;
	TWeakObjectPtr<class UUserWidget> MobileControls;
	UFUNCTION() void HandleArrived(int32 BodyIndex);

	// input trampolines
	void OnUp() { MenuMove(-1); }
	void OnDown() { MenuMove(1); }
	void OnLeft();
	void OnRight();
	void OnBody1() { SelectBody(0); }
	void OnBody2() { SelectBody(1); }
	void OnBody3() { SelectBody(2); }
	void OnConfirm();
	void OnBack();

	// scripted validation tour
	struct FCaptureStep
	{
		TFunction<bool()> Ready;
		TFunction<void()> Act;
		FString Shot;
	};
	void BuildCaptureTour();
	void TickCapture(float Dt);
	TArray<FCaptureStep> Capture;
	int32 CaptureStep = 0;
	float CaptureClock = 0.f;
	float StepClock = 0.f;
	bool bCapture = false;
	FString CaptureDir;

	UPROPERTY(Transient) TObjectPtr<AOdysseyTransitDirector> Director;
	UPROPERTY(Transient) TObjectPtr<UOdysseyLogoWidget> Logo;
	UPROPERTY(Transient) TObjectPtr<UOdysseySpaceHUDWidget> HUD;

	EOdysseySpaceFlow Flow = EOdysseySpaceFlow::Intro;
	int32 MenuIndex = 0;
	int32 SelectedBody = 1;
	float FlowTime = 0.f;
	float DescendTime = 0.f;
	bool bLevelOpened = false;
	bool bAwaitingShaders = true;
	float ShaderQuiet = 0.f;
	float ShaderWait = 0.f;
	bool bSkipIntroRequested = false;
	void LogPerf(const FString& Tag) const;
};
