// A planet or moon of the ODYSSEY space experience: surface sphere (+ optional atmosphere shell),
// axial spin, a parking orbit for the transit vehicle and the presentation data the navigation HUD
// shows. The surface/atmosphere materials receive the live sun direction ("SunDirection") so the
// night side, city lights and limb scattering follow the scene's directional light.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OdysseyCelestialBody.generated.h"

class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class ADirectionalLight;

UCLASS()
class ODYSSEYSPACE_API AOdysseyCelestialBody : public AActor
{
	GENERATED_BODY()

public:
	AOdysseyCelestialBody();

	// ---- identity / navigation data (Unreal-only presentation, not backend semantic ids)
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") FName BodyId;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") FText DisplayName;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") FText Designation;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") FText Summary;
	// Real mean radius (km) and the real distance from Earth (km), shown on the navigation display.
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") double RealRadiusKm = 6371.0;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") double RealDistanceFromEarthKm = 0.0;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") FLinearColor AccentColor = FLinearColor(0.38f, 0.75f, 0.82f);

	// ---- scene scale
	// Radius in world units (cm). The surface mesh is a sphere of radius MeshRadius (100 cm).
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") double Radius = 1000000.0;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Body") float MeshRadius = 100.f;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Body") float AtmosphereScale = 1.022f;
	// Parking orbit radius as a multiple of Radius, and its inclination (deg).
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") float OrbitFactor = 1.12f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") float OrbitInclination = 12.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") float OrbitPeriodSeconds = 150.f;
	// Axial spin of the surface (deg/s, presentation time).
	UPROPERTY(EditAnywhere, Category = "Odyssey|Body") float SpinDegreesPerSecond = 0.35f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") TObjectPtr<UStaticMeshComponent> Surface;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Body") TObjectPtr<UStaticMeshComponent> Atmosphere;

	double GetOrbitRadius() const { return Radius * OrbitFactor; }
	// Point on the parking orbit at angle Theta (radians) and the prograde direction there.
	FVector OrbitPoint(double Theta) const;
	FVector OrbitTangent(double Theta) const;
	// Orbit angle whose point is closest to the direction Dir (from the body centre).
	double OrbitAngleToward(const FVector& Dir) const;
	FVector OrbitNormal() const;

	// Direction from the body toward the sun (unit), from the scene's directional light.
	FVector GetSunDirection() const;

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void ApplyScale();
	void PushSun();
	void OrbitBasis(FVector& A, FVector& B) const;

	UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> Mids;
	UPROPERTY(Transient) TObjectPtr<ADirectionalLight> Sun;
};
