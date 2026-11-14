// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Third-person foundation (§17/§18): walk/run/stop/turn with CharacterMovement, a calm cinematic
// follow camera (lag, no shake), Enhanced Input, and the interactor. The Game Animation Sample /
// Motion Matching character is wired in a Blueprint child (BP_OdysseyPlayer) in the editor; this
// class exposes the state the animation layer needs (speed, interaction stance).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"

#include "OdysseyPlayerCharacter.generated.h"

class UCameraComponent;
class UInputAction;
class UInputMappingContext;
class UOdysseyInteractorComponent;
class USpringArmComponent;
struct FInputActionValue;

UCLASS(Blueprintable)
class ODYSSEYPLAYER_API AOdysseyPlayerCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AOdysseyPlayerCharacter();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Camera") TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Camera") TObjectPtr<UCameraComponent> FollowCamera;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Interaction") TObjectPtr<UOdysseyInteractorComponent> Interactor;

	// Enhanced Input assets (created in the editor under /Game/Systems/Input/).
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputMappingContext> DefaultMapping;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> MoveAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> LookAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> RunAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> InteractAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> CycleAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> BackAction;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Movement") float WalkSpeed = 190.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Movement") float RunSpeed = 430.f;

	// True while a physical panel is engaged (animation: interaction stance; movement is held).
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Interaction") bool bInInteractionStance = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Interaction") int32 SelectedControl = 0;

	// Direct entry points for on-screen touch controls: identical behaviour to the input-action
	// handlers, usable without the Enhanced Input assets.
	void TouchMove(const FVector2D& Axis);
	void TouchLook(const FVector2D& Axis);
	void TouchInteract();
	void TouchCycle();
	void TouchBack();

	// Place the pawn at a semantic anchor (used by the game mode; no backend traffic).
	void PlaceAt(const FTransform& Anchor);

protected:
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PawnClientRestart() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void Move(const FInputActionValue& Value);
	void Look(const FInputActionValue& Value);
	void StartRun(const FInputActionValue& Value);
	void StopRun(const FInputActionValue& Value);
	void Interact(const FInputActionValue& Value);
	void Cycle(const FInputActionValue& Value);
	void Back(const FInputActionValue& Value);
	class AOdysseyPowerConsole* ActiveConsole() const;
};
