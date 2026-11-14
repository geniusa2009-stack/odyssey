// Mission Control holographic table: a live, state-driven hologram above the physical projector.
// Nothing is baked into the projector mesh: Earth / Moon / Mars (planet textures through a
// hologram material), orbit rings, the transit vehicle marker, an animated trajectory of instanced
// beads, a station / incident marker, a projection beam, a scan disc and labels are separate
// components driven by dynamic material parameters every frame.
//
// States: Off -> Boot -> EarthOverview -> MissionPlanning -> Trajectory -> Simulation -> (loop),
// Incident while the backend reports an active incident (read-only GetIncidents query), then
// Resolved -> EarthOverview. Presentation only: no intents are sent.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OdysseyHoloTable.generated.h"

class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
class UTextRenderComponent;
class UMaterialInstanceDynamic;

UENUM(BlueprintType)
enum class EOdysseyHoloState : uint8
{
	Off,
	Boot,
	EarthOverview,
	MissionPlanning,
	Trajectory,
	Simulation,
	Incident,
	Resolved
};

UCLASS()
class ODYSSEYWORLD_API AOdysseyHoloTable : public AActor
{
	GENERATED_BODY()

public:
	AOdysseyHoloTable();

	// ---- content (assigned by Tools/Editor/Production/build_room_finish.py)
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMesh> RingMesh;      // unit torus, radius 100 cm
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMesh> BeadMesh;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMesh> DiscMesh;      // unit disc, radius 100 cm
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMesh> BeamMesh;      // open cone, base radius 100, height 100
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMesh> MarkerMesh;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UMaterialInterface> HoloMaterial;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UTexture> EarthTexture;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UTexture> MoonTexture;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Holo") TObjectPtr<UTexture> MarsTexture;

	// ---- behaviour
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Holo") bool bAutoProgram = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Holo") bool bFollowBackendIncidents = true;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Holo") float VolumeRadius = 95.f;  // cm
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Holo") float VolumeHeight = 70.f; // centre above the actor

	UFUNCTION(BlueprintCallable, Category = "Odyssey|Holo") void SetState(EOdysseyHoloState NewState);
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Holo") void SelectDestination(int32 Index);  // 1 = Moon, 2 = Mars
	UFUNCTION(BlueprintPure, Category = "Odyssey|Holo") EOdysseyHoloState GetState() const { return State; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Holo") int32 GetDestination() const { return Destination; }

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	struct FLayout
	{
		FVector Pos[3];
		float Radius[3];
		float BodyAlpha[3];
		float OrbitAlpha = 0.f;
		float TrajectoryAlpha = 0.f;
		float StationAlpha = 0.f;
		float CraftAlpha = 0.f;
	};

	FLayout TargetLayout() const;
	void Advance(float Dt);
	void PollBackend(float Dt);
	void Apply(float Dt);
	FVector Arc(float T) const;
	UMaterialInstanceDynamic* Mid(UStaticMeshComponent* C);
	void Param(UMaterialInstanceDynamic* M, float Intensity, const FLinearColor& Color) const;

	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> Beam;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> ScanDisc;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> Bodies0;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> Bodies1;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> Bodies2;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> MoonOrbit;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> StationRing;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> SelectRing;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> Craft;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UStaticMeshComponent> StationMarker;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UInstancedStaticMeshComponent> Beads;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UTextRenderComponent> Title;
	UPROPERTY(VisibleAnywhere, Category = "Odyssey|Holo") TObjectPtr<UTextRenderComponent> Detail;

	UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> BodyMids;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> BeamMid;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> DiscMid;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> OrbitMid;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> StationRingMid;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> SelectMid;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> CraftMid;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> MarkerMid;
	UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> BeadMid;

	EOdysseyHoloState State = EOdysseyHoloState::Off;
	float StateTime = 0.f;
	float Clock = 0.f;
	float PollClock = 0.f;
	float Power = 0.f;         // overall hologram presence 0..1
	float Alert = 0.f;         // 0 = ion, 1 = incident colouring
	int32 Destination = 1;
	bool bIncidentActive = false;
	FString IncidentText;
	FLayout Current;
	bool bLayoutInit = false;
};
