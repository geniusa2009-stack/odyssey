#include "OdysseyTouchControls.h"

#include "Brushes/SlateRoundedBoxBrush.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"

namespace
{
	const FLinearColor IonC(0.29f, 0.72f, 1.f);
	const FLinearColor WhiteC(0.93f, 0.95f, 0.97f);
	const FLinearColor GraphiteC(0.035f, 0.045f, 0.06f);

	FLinearColor A(FLinearColor C, float Alpha) { C.A = Alpha; return C; }

	void Disc(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, FVector2f Centre, float R, FLinearColor Fill, FLinearColor Edge, float EdgeW)
	{
		const FSlateRoundedBoxBrush Brush(Fill, R, Edge, EdgeW);
		FSlateDrawElement::MakeBox(Out, Layer, G.ToPaintGeometry(FVector2f(R * 2.f, R * 2.f), FSlateLayoutTransform(Centre - FVector2f(R, R))), &Brush);
	}

	void CentredText(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, FVector2f Centre, const FString& Text, const FSlateFontInfo& Font, FLinearColor C)
	{
		const FVector2f Size = FVector2f(FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Text, Font));
		FSlateDrawElement::MakeText(Out, Layer, G.ToPaintGeometry(Size, FSlateLayoutTransform(Centre - Size * 0.5f)), Text, Font, ESlateDrawEffect::None, C);
	}
}

bool UOdysseyTouchControls::ShouldUseTouch()
{
#if PLATFORM_ANDROID || PLATFORM_IOS
	return true;
#else
	return FParse::Param(FCommandLine::Get(), TEXT("OdysseyTouch"));
#endif
}

void UOdysseyTouchControls::NativeConstruct()
{
	Super::NativeConstruct();
	SetVisibility(ESlateVisibility::Visible);  // receives touches across the whole viewport
}

void UOdysseyTouchControls::SetButtons(const TArray<FOdysseyTouchButton>& InButtons)
{
	Buttons = InButtons;
	for (auto It = Fingers.CreateIterator(); It; ++It)
	{
		if (It.Value().Kind == EKind::Button) It.RemoveCurrent();  // a pressed button may no longer exist
	}
}

void UOdysseyTouchControls::SetButtonVisible(FName Id, bool bVisible)
{
	for (FOdysseyTouchButton& B : Buttons) if (B.Id == Id) B.bVisible = bVisible;
}

void UOdysseyTouchControls::SetButtonLabel(FName Id, const FString& Label)
{
	for (FOdysseyTouchButton& B : Buttons) if (B.Id == Id) B.Label = Label;
}

void UOdysseyTouchControls::SetStickEnabled(bool bEnabled)
{
	bStick = bEnabled;
	if (!bEnabled)
	{
		bStickActive = false;
		Move = FVector2D::ZeroVector;
	}
}

FVector2D UOdysseyTouchControls::ConsumeLook()
{
	const FVector2D Out = LookAccum;
	LookAccum = FVector2D::ZeroVector;
	return Out;
}

void UOdysseyTouchControls::Layout(const FVector2f& Size, FVector2f& OutMin, FVector2f& OutMax, float& OutS) const
{
	OutS = Size.Y;
	const float Margin = OutS * 0.035f;  // keeps controls off rounded corners / gesture edges
	OutMin = FVector2f(Margin, Margin);
	OutMax = Size - FVector2f(Margin, Margin);
}

FVector2f UOdysseyTouchControls::ButtonCentre(const FOdysseyTouchButton& B, const FVector2f& Min, const FVector2f& Max, float S) const
{
	const FVector2f AnchorPos = Min + (Max - Min) * B.Anchor;
	return AnchorPos + B.Offset * S;
}

const FOdysseyTouchButton* UOdysseyTouchControls::HitButton(const FVector2f& P, const FVector2f& Size) const
{
	FVector2f Min, Max;
	float S;
	Layout(Size, Min, Max, S);
	for (const FOdysseyTouchButton& B : Buttons)
	{
		// touch slop: the hit circle is 20 % larger than the drawn one
		if (B.bVisible && FVector2f::Distance(P, ButtonCentre(B, Min, Max, S)) <= B.Radius * S * 1.2f)
		{
			return &B;
		}
	}
	return nullptr;
}

bool UOdysseyTouchControls::InStickZone(const FVector2f& P, const FVector2f& Size) const
{
	return bStick && P.X < Size.X * 0.42f && P.Y > Size.Y * 0.3f;
}

FReply UOdysseyTouchControls::Begin(uint32 Pointer, const FGeometry& Geo, const FPointerEvent& Event)
{
	const FVector2f P = FVector2f(Geo.AbsoluteToLocal(Event.GetScreenSpacePosition()));
	const FVector2f Size = FVector2f(Geo.GetLocalSize());
	LastSize = Size;
	FFinger F;
	F.Start = F.Last = P;
	if (const FOdysseyTouchButton* B = HitButton(P, Size))
	{
		F.Kind = EKind::Button;
		F.Button = B->Id;
	}
	else if (InStickZone(P, Size) && !bStickActive)
	{
		F.Kind = EKind::Stick;
		bStickActive = true;
		StickCentre = P;
		StickKnob = P;
	}
	else if (bLook && P.X >= Size.X * 0.42f)
	{
		F.Kind = EKind::Look;
	}
	Fingers.Add(Pointer, F);
	return FReply::Handled();
}

FReply UOdysseyTouchControls::Update(uint32 Pointer, const FGeometry& Geo, const FPointerEvent& Event)
{
	FFinger* F = Fingers.Find(Pointer);
	if (!F)
	{
		return FReply::Unhandled();
	}
	const FVector2f P = FVector2f(Geo.AbsoluteToLocal(Event.GetScreenSpacePosition()));
	const float S = Geo.GetLocalSize().Y;
	if (F->Kind == EKind::Stick)
	{
		const float R = S * 0.11f;
		FVector2f D = P - StickCentre;
		if (D.Size() > R) D = D.GetSafeNormal() * R;
		StickKnob = StickCentre + D;
		Move = FVector2D(D.X / R, -D.Y / R);
	}
	else if (F->Kind == EKind::Look)
	{
		const FVector2f D = P - F->Last;
		// normalise to a 1080-unit-high screen so sensitivity is the same on every device
		LookAccum += FVector2D(D.X, D.Y) * (1080.f / FMath::Max(1.f, S)) * LookSensitivity;
	}
	F->Last = P;
	return FReply::Handled();
}

FReply UOdysseyTouchControls::End(uint32 Pointer, const FGeometry& Geo, const FPointerEvent& Event)
{
	FFinger F;
	if (!Fingers.RemoveAndCopyValue(Pointer, F))
	{
		return FReply::Unhandled();
	}
	const FVector2f P = FVector2f(Geo.AbsoluteToLocal(Event.GetScreenSpacePosition()));
	const FVector2f Size = FVector2f(Geo.GetLocalSize());
	switch (F.Kind)
	{
	case EKind::Stick:
		bStickActive = false;
		Move = FVector2D::ZeroVector;
		break;
	case EKind::Button:
		if (const FOdysseyTouchButton* B = HitButton(P, Size); B && B->Id == F.Button)
		{
			OnPressed.ExecuteIfBound(F.Button);
		}
		break;
	case EKind::Tap:
		if (FVector2f::Distance(P, F.Start) < Size.Y * 0.03f && OnTap.IsBound())
		{
			OnTap.Execute(P, Size);
		}
		break;
	default:
		break;
	}
	return FReply::Handled();
}

FReply UOdysseyTouchControls::NativeOnTouchStarted(const FGeometry& Geo, const FPointerEvent& E) { return Begin(E.GetPointerIndex(), Geo, E); }
FReply UOdysseyTouchControls::NativeOnTouchMoved(const FGeometry& Geo, const FPointerEvent& E) { return Update(E.GetPointerIndex(), Geo, E); }
FReply UOdysseyTouchControls::NativeOnTouchEnded(const FGeometry& Geo, const FPointerEvent& E) { return End(E.GetPointerIndex(), Geo, E); }

// Desktop testing (-OdysseyTouch): the mouse acts as one finger.
FReply UOdysseyTouchControls::NativeOnMouseButtonDown(const FGeometry& Geo, const FPointerEvent& E)
{
	return E.GetEffectingButton() == EKeys::LeftMouseButton ? Begin(1000, Geo, E).CaptureMouse(TakeWidget()) : FReply::Unhandled();
}
FReply UOdysseyTouchControls::NativeOnMouseMove(const FGeometry& Geo, const FPointerEvent& E) { return Update(1000, Geo, E); }
FReply UOdysseyTouchControls::NativeOnMouseButtonUp(const FGeometry& Geo, const FPointerEvent& E)
{
	return E.GetEffectingButton() == EKeys::LeftMouseButton ? End(1000, Geo, E).ReleaseMouseCapture() : FReply::Unhandled();
}

int32 UOdysseyTouchControls::NativePaint(const FPaintArgs& Args, const FGeometry& G, const FSlateRect& Cull,
	FSlateWindowElementList& Out, int32 LayerId, const FWidgetStyle& Style, bool bParentEnabled) const
{
	const FVector2f Size = FVector2f(G.GetLocalSize());
	LastSize = Size;
	FVector2f Min, Max;
	float S;
	Layout(Size, Min, Max, S);

	// movement stick: faint resting hint, full base + knob while held
	if (bStick)
	{
		const float R = S * 0.11f;
		if (bStickActive)
		{
			Disc(Out, LayerId, G, StickCentre, R, A(GraphiteC, 0.35f), A(WhiteC, 0.55f), 1.5f);
			Disc(Out, LayerId + 1, G, StickKnob, R * 0.42f, A(IonC, 0.55f), A(WhiteC, 0.9f), 1.5f);
		}
		else
		{
			const FVector2f Rest(Min.X + R * 1.25f, Max.Y - R * 1.25f);
			Disc(Out, LayerId, G, Rest, R, A(GraphiteC, 0.18f), A(WhiteC, 0.28f), 1.f);
			Disc(Out, LayerId + 1, G, Rest, R * 0.42f, A(WhiteC, 0.12f), A(WhiteC, 0.35f), 1.f);
			CentredText(Out, LayerId + 2, G, Rest + FVector2f(0.f, R * 1.25f), TEXT("MOVE"),
				FCoreStyle::GetDefaultFontStyle("Bold", FMath::Max(9.f, S * 0.017f)), A(WhiteC, 0.55f));
		}
	}
	if (bLook)
	{
		CentredText(Out, LayerId, G, FVector2f(Size.X * 0.71f, Max.Y - S * 0.015f), TEXT("DRAG TO LOOK"),
			FCoreStyle::GetDefaultFontStyle("Bold", FMath::Max(9.f, S * 0.015f)), A(WhiteC, 0.32f));
	}

	if (!Status.IsEmpty())
	{
		const FSlateFontInfo F = FCoreStyle::GetDefaultFontStyle("Bold", FMath::Max(9.f, S * 0.017f));
		const FVector2f TS = FVector2f(FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Status, F));
		const FVector2f C(Size.X * 0.5f, Min.Y + TS.Y);
		const FSlateRoundedBoxBrush Chip(A(GraphiteC, 0.6f), TS.Y, A(IonC, 0.7f), 1.f);
		const FVector2f Pad(S * 0.02f, S * 0.008f);
		FSlateDrawElement::MakeBox(Out, LayerId, G.ToPaintGeometry(TS + Pad * 2.f, FSlateLayoutTransform(C - TS * 0.5f - Pad)), &Chip);
		CentredText(Out, LayerId + 1, G, C, Status, F, A(WhiteC, 0.92f));
	}
	if (!Prompt.IsEmpty())
	{
		CentredText(Out, LayerId + 1, G, FVector2f(Size.X * 0.5f, Size.Y * 0.74f), Prompt,
			FCoreStyle::GetDefaultFontStyle("Bold", FMath::Max(10.f, S * 0.026f)), WhiteC);
	}

	TSet<FName> Held;
	for (const TPair<uint32, FFinger>& F : Fingers)
	{
		if (F.Value.Kind == EKind::Button) Held.Add(F.Value.Button);
	}
	for (const FOdysseyTouchButton& B : Buttons)
	{
		if (!B.bVisible) continue;
		const FVector2f C = ButtonCentre(B, Min, Max, S);
		const float R = B.Radius * S;
		const bool bDown = Held.Contains(B.Id);
		const FLinearColor Fill = B.bPrimary ? A(IonC, bDown ? 0.95f : 0.7f) : A(GraphiteC, bDown ? 0.85f : 0.55f);
		const FLinearColor Edge = B.bPrimary ? A(WhiteC, 0.95f) : A(bDown ? IonC : WhiteC, 0.7f);
		Disc(Out, LayerId + 3, G, C, R * (bDown ? 0.94f : 1.f), Fill, Edge, 1.5f);
		const float FontSize = FMath::Max(9.f, S * (B.Label.Len() > 7 ? 0.0165f : 0.021f));
		CentredText(Out, LayerId + 4, G, C, B.Label, FCoreStyle::GetDefaultFontStyle("Bold", FontSize), B.bPrimary ? GraphiteC : WhiteC);
	}
	return Super::NativePaint(Args, G, Cull, Out, LayerId + 5, Style, bParentEnabled);
}
