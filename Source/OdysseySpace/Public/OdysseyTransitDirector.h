// Orchestrates the ODYSSEY space experience: the transit vehicle's parking orbits and transfers
// between celestial bodies, and the camera language (menu hero shot, orbit vista, planet view and a
// shot sequence for every transfer: departure chase, over-the-shoulder cruise toward the target,
// flip manoeuvre close-up, arrival reveal). The director is the player's view target.
//
// A transfer is a cubic Bezier from the vehicle's position on its parking orbit to an arrival
// point on the target's parking orbit, kept clear of every body, flown with a trapezoidal speed
// profile: departure burn -> coast -> 180 deg flip -> arrival (retro) burn. Durations are
// presentation time; the telemetry maps progress onto real distances and mission time.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OdysseyTransitDirector.generated.h"

class AOdysseyCelestialBody;
class AOdysseyTransitVehicle;
class UCameraComponent;

UENUM(BlueprintType)
enum class EOdysseyTransitPhase : uint8
{
	Parked,
	Aligning,      // orbiting faster until the departure direction faces the target
	DepartureBurn,
	Coast,
	FlipManeuver,
	ArrivalBurn
};

UENUM(BlueprintType)
enum class EOdysseyDirectorView : uint8
{
	Menu,        // hero shot of the current body, framed to leave room for the menu
	OrbitVista,  // vehicle in the foreground against the planet limb
	PlanetView,  // the whole current body
	Travel       // automatic during a transfer
};

USTRUCT(BlueprintType)
struct FOdysseyTransitTelemetry
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly) EOdysseyTransitPhase Phase = EOdysseyTransitPhase::Parked;
	UPROPERTY(BlueprintReadOnly) int32 Origin = 0;
	UPROPERTY(BlueprintReadOnly) int32 Target = 0;
	UPROPERTY(BlueprintReadOnly) float Progress = 0.f;           // 0..1 of the transfer
	UPROPERTY(BlueprintReadOnly) double VelocityKms = 0.0;       // presented relative velocity
	UPROPERTY(BlueprintReadOnly) double DistanceRemainingKm = 0.0;
	UPROPERTY(BlueprintReadOnly) double LegDistanceKm = 0.0;
	UPROPERTY(BlueprintReadOnly) double MissionHours = 0.0;      // elapsed transfer time (story)
	UPROPERTY(BlueprintReadOnly) double LegHours = 0.0;          // full transfer time (story)
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyTransitEvent, int32, BodyIndex);

UCLASS()
class ODYSSEYSPACE_API AOdysseyTransitDirector : public AActor
{
	GENERATED_BODY()

public:
	AOdysseyTransitDirector();

	// Earth first. Index order is the navigation display order.
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Transit") TArray<TObjectPtr<AOdysseyCelestialBody>> Bodies;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Transit") TObjectPtr<AOdysseyTransitVehicle> Vehicle;
	// Sky sphere and sun disc are kept centred on the camera so they read as infinitely far.
	UPROPERTY(EditAnywhere, Category = "Odyssey|Transit") TObjectPtr<AActor> SkyActor;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Transit") TObjectPtr<AActor> SunDiscActor;
	UPROPERTY(EditAnywhere, Category = "Odyssey|Transit") double SunDiscDistance = 8.0e7;

	UPROPERTY(EditAnywhere, Category = "Odyssey|Transit") float ShortLegSeconds = 17.f;  // Earth <-> Moon
	UPROPERTY(EditAnywhere, Category = "Odyssey|Transit") float LongLegSeconds = 24.f;   // any leg to/from Mars
	UPROPERTY(EditAnywhere, Category = "Odyssey|Transit") int32 StartBody = 0;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey|Transit") TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Transit") FOdysseyTransitEvent OnDeparted;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Transit") FOdysseyTransitEvent OnArrived;

	UFUNCTION(BlueprintCallable, Category = "Odyssey|Transit") bool BeginTravel(int32 TargetIndex);
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Transit") void SetView(EOdysseyDirectorView NewView);
	UFUNCTION(BlueprintPure, Category = "Odyssey|Transit") EOdysseyDirectorView GetView() const { return View; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Transit") bool IsTraveling() const { return bTraveling; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Transit") int32 GetCurrentBody() const { return Current; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Transit") int32 NumBodies() const { return Bodies.Num(); }
	AOdysseyCelestialBody* GetBody(int32 Index) const;
	const FOdysseyTransitTelemetry& GetTelemetry() const { return Telemetry; }

	// Real distance between two bodies (km) and the story transfer time (hours).
	double RealDistanceKm(int32 A, int32 B) const;
	double TransferHours(int32 A, int32 B) const;

	// Seconds since the last arrival (drives the arrival banner).
	float SinceArrival() const { return SinceArrivalSeconds; }

	// Debug / capture helpers.
	void JumpToTravelProgress(float U);

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void TickParked(float Dt);
	void TickTravel(float Dt);
	void UpdateCamera(float Dt);
	void KeepSkyOnCamera();
	bool LegIsLong(int32 A, int32 B) const;

	// trapezoidal speed profile: progress along the path and normalised speed for time fraction U
	void Profile(float U, double& S, double& Speed) const;
	FVector Bezier(double S) const;
	FVector BezierTangent(double S) const;
	bool PathClear(const FVector& P1, const FVector& P2) const;

	FTransform ShotTransform(int32 Shot, const FVector& V, const FVector& Fwd, const FVector& Up) const;
	FTransform MenuTransform(double T) const;
	FTransform VistaTransform(double T) const;
	FTransform PlanetTransform(double T) const;

	EOdysseyDirectorView View = EOdysseyDirectorView::Menu;
	EOdysseyDirectorView PreviousView = EOdysseyDirectorView::Menu;
	int32 Current = 0;
	int32 Target = 0;
	bool bTraveling = false;
	double OrbitTheta = 0.0;
	double OrbitSpeedScale = 1.0;
	float LegTime = 0.f;
	float LegDuration = 1.f;
	float SinceArrivalSeconds = 1000.f;
	double Clock = 0.0;
	FVector P0, P1, P2, P3;
	TArray<double> ArcLength;   // cumulative Bezier length, 0..1, for arc-length parameterisation
	double ArrivalTheta = 0.0;
	bool bAligning = false;
	int32 PendingTarget = INDEX_NONE;
	void StartTransfer();
	double ArcToBezierT(double S) const;
	FVector LegUp = FVector::UpVector;
	FQuat VehicleQuat = FQuat::Identity;

	FTransform BlendFrom;
	float ViewBlend = 1.f;
	float ViewBlendDuration = 2.5f;
	bool bHasCamera = false;
	FTransform LastCamera;

	FOdysseyTransitTelemetry Telemetry;
};
