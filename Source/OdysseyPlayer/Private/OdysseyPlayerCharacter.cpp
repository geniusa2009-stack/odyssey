// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyPlayerCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputActionValue.h"
#include "OdysseyInteractableComponent.h"
#include "OdysseyInteractorComponent.h"
#include "OdysseyPowerConsole.h"

AOdysseyPlayerCharacter::AOdysseyPlayerCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	GetCapsuleComponent()->InitCapsuleSize(34.f, 90.f);
	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;

	UCharacterMovementComponent* Movement = GetCharacterMovement();
	Movement->bOrientRotationToMovement = true;
	Movement->RotationRate = FRotator(0.f, 420.f, 0.f);
	Movement->MaxWalkSpeed = WalkSpeed;
	Movement->MinAnalogWalkSpeed = 40.f;
	Movement->BrakingDecelerationWalking = 1400.f;
	Movement->GroundFriction = 6.f;
	Movement->bUseSeparateBrakingFriction = false;

	// Calm, readable framing: slight over-the-shoulder offset, positional lag, no rotation lag, no shake.
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 340.f;
	CameraBoom->SocketOffset = FVector(0.f, 45.f, 55.f);
	CameraBoom->bUsePawnControlRotation = true;
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 9.f;
	CameraBoom->bEnableCameraRotationLag = false;
	CameraBoom->ProbeSize = 14.f;

	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false;
	FollowCamera->SetFieldOfView(72.f);

	Interactor = CreateDefaultSubobject<UOdysseyInteractorComponent>(TEXT("Interactor"));
}

void AOdysseyPlayerCharacter::PawnClientRestart()
{
	Super::PawnClientRestart();
	if (const APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* EI = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			if (DefaultMapping)
			{
				EI->AddMappingContext(DefaultMapping, 0);
			}
		}
	}
}

void AOdysseyPlayerCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!EIC)
	{
		return;
	}
	if (MoveAction) EIC->BindAction(MoveAction, ETriggerEvent::Triggered, this, &AOdysseyPlayerCharacter::Move);
	if (LookAction) EIC->BindAction(LookAction, ETriggerEvent::Triggered, this, &AOdysseyPlayerCharacter::Look);
	if (RunAction)
	{
		EIC->BindAction(RunAction, ETriggerEvent::Started, this, &AOdysseyPlayerCharacter::StartRun);
		EIC->BindAction(RunAction, ETriggerEvent::Completed, this, &AOdysseyPlayerCharacter::StopRun);
	}
	if (InteractAction) EIC->BindAction(InteractAction, ETriggerEvent::Started, this, &AOdysseyPlayerCharacter::Interact);
	if (CycleAction) EIC->BindAction(CycleAction, ETriggerEvent::Started, this, &AOdysseyPlayerCharacter::Cycle);
	if (BackAction) EIC->BindAction(BackAction, ETriggerEvent::Started, this, &AOdysseyPlayerCharacter::Back);
}

void AOdysseyPlayerCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const AOdysseyPowerConsole* Console = ActiveConsole();
	bInInteractionStance = Console && Console->IsPanelActive();
}

AOdysseyPowerConsole* AOdysseyPlayerCharacter::ActiveConsole() const
{
	const UOdysseyInteractableComponent* F = Interactor ? Interactor->GetFocused() : nullptr;
	return F ? Cast<AOdysseyPowerConsole>(F->GetOwner()) : nullptr;
}

void AOdysseyPlayerCharacter::Move(const FInputActionValue& Value)
{
	if (bInInteractionStance || !Controller)
	{
		return;
	}
	const FVector2D Axis = Value.Get<FVector2D>();
	const FRotator Yaw(0.f, Controller->GetControlRotation().Yaw, 0.f);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), Axis.Y);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), Axis.X);
}

void AOdysseyPlayerCharacter::Look(const FInputActionValue& Value)
{
	const FVector2D Axis = Value.Get<FVector2D>();
	AddControllerYawInput(Axis.X);
	AddControllerPitchInput(Axis.Y);
}

void AOdysseyPlayerCharacter::StartRun(const FInputActionValue&)
{
	GetCharacterMovement()->MaxWalkSpeed = RunSpeed;
}

void AOdysseyPlayerCharacter::StopRun(const FInputActionValue&)
{
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
}

void AOdysseyPlayerCharacter::Interact(const FInputActionValue&)
{
	if (AOdysseyPowerConsole* Console = ActiveConsole())
	{
		if (Console->IsPanelActive())
		{
			Console->PressControl(SelectedControl);
			return;
		}
	}
	SelectedControl = 0;
	Interactor->Interact();
}

void AOdysseyPlayerCharacter::Cycle(const FInputActionValue&)
{
	if (const AOdysseyPowerConsole* Console = ActiveConsole())
	{
		const int32 Count = FMath::Max(1, Console->Controls.Num());
		SelectedControl = (SelectedControl + 1) % Count;
	}
}

void AOdysseyPlayerCharacter::Back(const FInputActionValue&)
{
	if (AOdysseyPowerConsole* Console = ActiveConsole())
	{
		Console->SetPanelActive(false);
	}
}

void AOdysseyPlayerCharacter::PlaceAt(const FTransform& Anchor)
{
	const FVector Location = Anchor.GetLocation() + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
	SetActorLocationAndRotation(Location, FRotator(0.f, Anchor.Rotator().Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
	if (Controller)
	{
		Controller->SetControlRotation(FRotator(-10.f, Anchor.Rotator().Yaw, 0.f));
	}
}

void AOdysseyPlayerCharacter::MobileMove(FVector2D Axis) { Move(FInputActionValue(Axis)); }
void AOdysseyPlayerCharacter::MobileLook(FVector2D Axis) { Look(FInputActionValue(Axis)); }
void AOdysseyPlayerCharacter::MobileAction(int32 Index)
{
	const FInputActionValue Empty;
	if (Index == 0) Interact(Empty);
	else if (Index == 1) Cycle(Empty);
	else if (Index == 2) Back(Empty);
}
