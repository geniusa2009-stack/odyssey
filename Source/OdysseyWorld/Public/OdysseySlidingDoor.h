// Station sliding door (Unreal-only presentation + traversal; no backend semantics).
// Frame + two panels that slide apart along local X when a pawn enters the presence volume,
// hold open while occupied, then close with an eased motion. Panels block when closed and clear
// the opening completely when open. Status lights: ion = ready, amber = moving / held, red = locked.
// Local axes: X along the wall, Y through the doorway, Z up; pivot at the opening centre, floor level.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OdysseySlidingDoor.generated.h"

class UBoxComponent;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;

UENUM(BlueprintType)
enum class EOdysseyDoorState : uint8
{
	Closed,
	Opening,
	Open,
	Closing,
	Locked
};

UCLASS()
class ODYSSEYWORLD_API AOdysseySlidingDoor : public AActor
{
	GENERATED_BODY()

public:
	AOdysseySlidingDoor();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Door") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Door") TObjectPtr<UStaticMeshComponent> Frame;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Door") TObjectPtr<UStaticMeshComponent> PanelLeft;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Door") TObjectPtr<UStaticMeshComponent> PanelRight;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Door") TObjectPtr<UStaticMeshComponent> StatusLeft;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Door") TObjectPtr<UStaticMeshComponent> StatusRight;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Door") TObjectPtr<UBoxComponent> Presence;

	// How far each panel travels (cm, local X) and how long a full stroke takes.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Door") float OpenDistance = 112.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Door") float StrokeSeconds = 0.85f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Door") float HoldOpenSeconds = 1.2f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Door") bool bLocked = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Door") FText AccessLabel;

	UFUNCTION(BlueprintCallable, Category = "Odyssey|Door") void SetLocked(bool bInLocked) { bLocked = bInLocked; }
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Door") void ForceOpen(bool bInForce) { bForceOpen = bInForce; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Door") EOdysseyDoorState GetDoorState() const { return State; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Door") float GetOpenAlpha() const { return Alpha; }

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void ApplyPanels();
	void ApplyStatus();
	bool IsOccupied() const;

	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> StatusMidL;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> StatusMidR;
	FVector LeftClosed = FVector::ZeroVector;
	FVector RightClosed = FVector::ZeroVector;
	EOdysseyDoorState State = EOdysseyDoorState::Closed;
	float Alpha = 0.f;        // 0 closed .. 1 open (linear stroke position)
	float SinceOccupied = 100.f;
	bool bForceOpen = false;
};
