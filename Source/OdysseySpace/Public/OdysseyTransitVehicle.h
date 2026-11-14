// OTV-1 "Meridian": the ODYSSEY crew transit vehicle that carries the player between Earth, the
// Moon and Mars. Pure presentation: hull mesh, three engine plumes driven by Thrust, an engine
// light, reaction-control flashes for the flip manoeuvre and blinking navigation lights.
// Local axes: +X = nose (direction of flight), +Z = dorsal. Engines exhaust toward -X.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OdysseyTransitVehicle.generated.h"

class UStaticMeshComponent;
class UPointLightComponent;
class UMaterialInstanceDynamic;

UCLASS()
class ODYSSEYSPACE_API AOdysseyTransitVehicle : public AActor
{
	GENERATED_BODY()

public:
	AOdysseyTransitVehicle();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Vehicle") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Vehicle") TObjectPtr<UStaticMeshComponent> Hull;
	// Plume mesh: pivot at the nozzle exit plane, extends along -X; X scale follows Thrust.
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Vehicle") TObjectPtr<UStaticMeshComponent> Plume;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Vehicle") TObjectPtr<UStaticMeshComponent> RCS;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Vehicle") TObjectPtr<UPointLightComponent> EngineLight;

	// Overall length (cm) - used by the director to frame camera shots.
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Vehicle") float Length = 6200.f;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Vehicle") float EngineLightIntensity = 400000.f;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Vehicle") float NavBlinkPeriod = 1.6f;

	UFUNCTION(BlueprintCallable, Category = "Odyssey|Vehicle") void SetThrust(float InThrust) { TargetThrust = FMath::Clamp(InThrust, 0.f, 1.f); }
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Vehicle") void SetRCS(float InRCS) { TargetRCS = FMath::Clamp(InRCS, 0.f, 1.f); }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Vehicle") float GetThrust() const { return Thrust; }

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> PlumeMid;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> RcsMid;
	UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> HullMids;
	float Thrust = 0.f;
	float TargetThrust = 0.f;
	float RcsLevel = 0.f;
	float TargetRCS = 0.f;
	float Clock = 0.f;
};
