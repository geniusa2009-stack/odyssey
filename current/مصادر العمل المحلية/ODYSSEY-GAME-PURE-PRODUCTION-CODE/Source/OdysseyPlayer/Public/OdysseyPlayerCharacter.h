




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

	
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputMappingContext> DefaultMapping;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> MoveAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> LookAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> RunAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> InteractAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> CycleAction;
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Input") TObjectPtr<UInputAction> BackAction;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Movement") float WalkSpeed = 190.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Movement") float RunSpeed = 430.f;

	
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Interaction") bool bInInteractionStance = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Interaction") int32 SelectedControl = 0;

	
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
