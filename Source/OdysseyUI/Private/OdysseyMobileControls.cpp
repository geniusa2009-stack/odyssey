#include "OdysseyMobileControls.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/SafeZone.h"
#include "Components/TextBlock.h"
#include "Engine/Engine.h"
#include "Framework/Application/SlateApplication.h"
#include "Engine/World.h"
#include "Engine/GameViewportClient.h"
#include "Rendering/DrawElements.h"
#include "Misc/CoreDelegates.h"
#include "Styling/CoreStyle.h"

namespace
{
	const FLinearColor Ion(0.16f, 0.63f, 0.82f, 1.f);
	void Place(UCanvasPanel* Canvas, UWidget* Child, float L, float T, float R, float B)
	{
		UCanvasPanelSlot* Slot = Canvas->AddChildToCanvas(Child);
		Slot->SetAnchors(FAnchors(L, T, R, B));
		Slot->SetOffsets(FMargin(8.f));
	}
}

void UOdysseyTouchSurface::NativeConstruct()
{
	Super::NativeConstruct();
	BackgroundHandle = FCoreDelegates::ApplicationWillEnterBackgroundDelegate.AddUObject(this, &UOdysseyTouchSurface::ResetTouch);
}

void UOdysseyTouchSurface::NativeDestruct()
{
	FCoreDelegates::ApplicationWillEnterBackgroundDelegate.Remove(BackgroundHandle);
	ResetTouch();
	Super::NativeDestruct();
}

void UOdysseyTouchSurface::ResetTouch()
{
	Finger = INDEX_NONE;
	Axis = FVector2D::ZeroVector;
	if (bMovement && OnAxis) OnAxis(Axis);
}

FReply UOdysseyTouchSurface::NativeOnTouchStarted(const FGeometry& G, const FPointerEvent& E)
{
	if (Finger != INDEX_NONE) return FReply::Unhandled();
	Finger = E.GetPointerIndex();
	Origin = Last = G.AbsoluteToLocal(E.GetScreenSpacePosition());
	Axis = FVector2D::ZeroVector;
	return FReply::Handled().CaptureMouse(TakeWidget());
}

FReply UOdysseyTouchSurface::NativeOnTouchMoved(const FGeometry& G, const FPointerEvent& E)
{
	if (E.GetPointerIndex() != Finger) return FReply::Unhandled();
	const FVector2D Now = G.AbsoluteToLocal(E.GetScreenSpacePosition());
	if (bMovement)
	{
		const float Radius = FMath::Max(40.f, FMath::Min(G.GetLocalSize().X, G.GetLocalSize().Y) * 0.25f);
		Axis = ((Now - Origin) / Radius).GetClampedToMaxSize(1.f);
	}
	else if (OnAxis)
	{
		// Normalize sensitivity across display density and resolution; no per-frame multiplier.
		OnAxis((Now - Last) / FMath::Max(1.f, G.GetLocalSize().Y) * 65.f);
	}
	Last = Now;
	return FReply::Handled();
}

FReply UOdysseyTouchSurface::NativeOnTouchEnded(const FGeometry&, const FPointerEvent& E)
{
	if (E.GetPointerIndex() != Finger) return FReply::Unhandled();
	ResetTouch();
	return FReply::Handled().ReleaseMouseCapture();
}

void UOdysseyTouchSurface::NativeOnMouseCaptureLost(const FCaptureLostEvent& E)
{
	Super::NativeOnMouseCaptureLost(E);
	ResetTouch();
}

void UOdysseyTouchSurface::NativeTick(const FGeometry& G, float Dt)
{
	Super::NativeTick(G, Dt);
	// Clear a held stick when the app backgrounds; never retain motion across resume.
	if (!FSlateApplication::IsInitialized() || !FSlateApplication::Get().IsActive()) ResetTouch();
	if (bMovement && Finger != INDEX_NONE && OnAxis) OnAxis(FVector2D(Axis.X, -Axis.Y));
}

int32 UOdysseyTouchSurface::NativePaint(const FPaintArgs& A, const FGeometry& G, const FSlateRect& C,
	FSlateWindowElementList& D, int32 L, const FWidgetStyle& S, bool Enabled) const
{
	Super::NativePaint(A, G, C, D, L, S, Enabled);
	const FVector2D Size = G.GetLocalSize();
	const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle("Regular", 16);
	FSlateDrawElement::MakeText(D, L + 1, G.ToPaintGeometry(), bMovement ? TEXT("MOVE") : TEXT("DRAG TO LOOK"), Font, ESlateDrawEffect::None, Ion);
	if (bMovement)
	{
		const float Radius = FMath::Max(40.f, FMath::Min(Size.X, Size.Y) * 0.25f);
		const FVector2D Center = Finger == INDEX_NONE ? Size * 0.5f : Origin;
		TArray<FVector2f> Ring;
		for (int32 I = 0; I <= 32; ++I)
		{
			const float T = 2.f * PI * I / 32.f;
			Ring.Add(FVector2f(Center + FVector2D(FMath::Cos(T), FMath::Sin(T)) * Radius));
		}
		FSlateDrawElement::MakeLines(D, L + 1, G.ToPaintGeometry(), Ring, ESlateDrawEffect::None, Ion.CopyWithNewOpacity(0.5f), true, 2.f);
		const FVector2D Knob = Center + Axis * Radius - FVector2D(12.f, 12.f);
		FSlateDrawElement::MakeBox(D, L + 2, G.ToPaintGeometry(FVector2D(24.f, 24.f), FSlateLayoutTransform(Knob)), FCoreStyle::Get().GetBrush("WhiteBrush"), ESlateDrawEffect::None, Ion);
	}
	return L + 3;
}

TSharedRef<SWidget> UOdysseyMobileControls::RebuildWidget()
{
	if (!WidgetTree) WidgetTree = NewObject<UWidgetTree>(this, TEXT("MobileWidgetTree"));
	if (!WidgetTree->RootWidget)
	{
		USafeZone* Safe = WidgetTree->ConstructWidget<USafeZone>();
		WidgetTree->RootWidget = Safe;
		UCanvasPanel* Canvas = WidgetTree->ConstructWidget<UCanvasPanel>();
		Safe->AddChild(Canvas);
		HeadingText = WidgetTree->ConstructWidget<UTextBlock>();
		HeadingText->SetFont(FCoreStyle::GetDefaultFontStyle("Bold", 24));
		HeadingText->SetColorAndOpacity(FSlateColor(Ion));
		Place(Canvas, HeadingText, 0.03f, 0.02f, 0.97f, 0.14f);
		DetailText = WidgetTree->ConstructWidget<UTextBlock>();
		DetailText->SetFont(FCoreStyle::GetDefaultFontStyle("Regular", 17));
		DetailText->SetAutoWrapText(true);
		Place(Canvas, DetailText, 0.03f, 0.14f, 0.97f, 0.34f);
		if (bStation)
		{
			UOdysseyTouchSurface* Move = CreateWidget<UOdysseyTouchSurface>(GetOwningPlayer());
			Move->bMovement = true;
			Move->SetVisibility(ESlateVisibility::Visible);
			Move->OnAxis = [this](FVector2D V) { if (OnMove) OnMove(V); };
			Place(Canvas, Move, 0.02f, 0.40f, 0.35f, 0.97f);
			UOdysseyTouchSurface* Look = CreateWidget<UOdysseyTouchSurface>(GetOwningPlayer());
			Look->SetVisibility(ESlateVisibility::Visible);
			Look->OnAxis = [this](FVector2D V) { if (OnLook) OnLook(V); };
			Place(Canvas, Look, 0.43f, 0.35f, 0.98f, 0.69f);
		}
		for (int32 I = 0; I < 8; ++I)
		{
			UButton* B = WidgetTree->ConstructWidget<UButton>();
			B->SetBackgroundColor(FLinearColor(0.035f, 0.06f, 0.085f, 0.94f));
			B->SetIsFocusable(false);
			UTextBlock* Text = WidgetTree->ConstructWidget<UTextBlock>();
			Text->SetFont(FCoreStyle::GetDefaultFontStyle("Bold", 18));
			Text->SetColorAndOpacity(FSlateColor(FLinearColor::White));
			Text->SetJustification(ETextJustify::Center);
			Text->SetAutoWrapText(true);
			B->AddChild(Text);
			const float Left = bStation ? 0.43f : 0.02f;
			const float Width = bStation ? 0.1375f : 0.24f;
			const float X = Left + (I % 4) * Width;
			const float Y = 0.69f + (I / 4) * 0.15f;
			Place(Canvas, B, X, Y, X + Width, Y + 0.15f);
			Buttons.Add(B);
			Labels.Add(Text);
			B->SetVisibility(ESlateVisibility::Collapsed);
		}
		Buttons[0]->OnClicked.AddDynamic(this, &UOdysseyMobileControls::Action0);
		Buttons[1]->OnClicked.AddDynamic(this, &UOdysseyMobileControls::Action1);
		Buttons[2]->OnClicked.AddDynamic(this, &UOdysseyMobileControls::Action2);
		Buttons[3]->OnClicked.AddDynamic(this, &UOdysseyMobileControls::Action3);
		Buttons[4]->OnClicked.AddDynamic(this, &UOdysseyMobileControls::Action4);
		Buttons[5]->OnClicked.AddDynamic(this, &UOdysseyMobileControls::Action5);
		Buttons[6]->OnClicked.AddDynamic(this, &UOdysseyMobileControls::Action6);
		Buttons[7]->OnClicked.AddDynamic(this, &UOdysseyMobileControls::Action7);
	}
	return Super::RebuildWidget();
}

void UOdysseyMobileControls::SetAction(int32 I, const FString& Label, bool Enabled)
{
	if (!Buttons.IsValidIndex(I)) return;
	Labels[I]->SetText(FText::FromString(Label));
	Buttons[I]->SetVisibility(Label.IsEmpty() ? ESlateVisibility::Collapsed : ESlateVisibility::Visible);
	Buttons[I]->SetIsEnabled(Enabled);
}

void UOdysseyMobileControls::SetHeading(const FString& Heading, const FString& Detail)
{
	if (HeadingText) HeadingText->SetText(FText::FromString(Heading));
	if (DetailText) DetailText->SetText(FText::FromString(Detail));
}

void UOdysseyMobileControls::Action0() { if (OnAction) OnAction(0); }
void UOdysseyMobileControls::Action1() { if (OnAction) OnAction(1); }
void UOdysseyMobileControls::Action2() { if (OnAction) OnAction(2); }
void UOdysseyMobileControls::Action3() { if (OnAction) OnAction(3); }
void UOdysseyMobileControls::Action4() { if (OnAction) OnAction(4); }
void UOdysseyMobileControls::Action5() { if (OnAction) OnAction(5); }
void UOdysseyMobileControls::Action6() { if (OnAction) OnAction(6); }
void UOdysseyMobileControls::Action7() { if (OnAction) OnAction(7); }
