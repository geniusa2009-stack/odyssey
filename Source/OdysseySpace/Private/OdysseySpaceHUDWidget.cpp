#include "OdysseySpaceHUDWidget.h"

#include "Internationalization/Text.h"
#include "OdysseyBrandPaint.h"
#include "OdysseyCelestialBody.h"
#include "OdysseySpaceGameMode.h"
#include "OdysseyTransitDirector.h"

namespace
{
	using namespace OdysseyBrand;

	float Ramp(float T, float A, float B)
	{
		const float X = FMath::Clamp((T - A) / (B - A), 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}

	FString Km(double V)
	{
		if (V >= 1.0e6)
		{
			return FString::Printf(TEXT("%.1f M KM"), V / 1.0e6);
		}
		return FText::AsNumber((int64)FMath::RoundToDouble(V)).ToString() + TEXT(" KM");
	}

	FString Duration(double Hours)
	{
		const int64 Total = (int64)FMath::RoundToDouble(Hours * 60.0);
		const int64 D = Total / (24 * 60), H = (Total / 60) % 24, M = Total % 60;
		return FString::Printf(TEXT("%03lldD %02lldH %02lldM"), D, H, M);
	}

	FString PhaseName(EOdysseyTransitPhase P)
	{
		switch (P)
		{
		case EOdysseyTransitPhase::Aligning: return TEXT("ALIGNING FOR TRANSFER WINDOW");
		case EOdysseyTransitPhase::DepartureBurn: return TEXT("DEPARTURE BURN");
		case EOdysseyTransitPhase::Coast: return TEXT("BALLISTIC COAST");
		case EOdysseyTransitPhase::FlipManeuver: return TEXT("FLIP MANEUVER");
		case EOdysseyTransitPhase::ArrivalBurn: return TEXT("ORBIT INSERTION BURN");
		default: return TEXT("PARKING ORBIT");
		}
	}

	FString Upper(const FText& T) { return T.ToString().ToUpper(); }

	TArray<FString> Wrap(const FString& Text, const FSlateFontInfo& FontInfo, float MaxWidth)
	{
		TArray<FString> Words, Lines;
		Text.ParseIntoArray(Words, TEXT(" "));
		FString Line;
		for (const FString& W : Words)
		{
			const FString Try = Line.IsEmpty() ? W : Line + TEXT(" ") + W;
			if (!Line.IsEmpty() && Measure(Try, FontInfo).X > MaxWidth)
			{
				Lines.Add(Line);
				Line = W;
			}
			else
			{
				Line = Try;
			}
		}
		if (!Line.IsEmpty()) Lines.Add(Line);
		return Lines;
	}

	void Badge(const FPainter& P, float S, float Alpha)
	{
		FPainter Q = P;
		Q.Opacity = Alpha;
		const FVector2f Origin(S * 0.035f, S * 0.04f);
		const float H = S * 0.022f;
		Mark(Q, Origin + FVector2f(H * 0.66f, H * 0.5f), H * 1.32f, 1.f, 1.f, Ion(1.f), FMath::Max(1.5f, H * 0.09f));
		Wordmark(Q, Origin + FVector2f(H * 1.32f + H * 0.6f, 0.f), H, 0.2f, 1.f, White(1.f), FMath::Max(1.5f, H * 0.11f));
		Q.Text(Origin + FVector2f(H * 1.92f, H * 1.35f), TEXT("EARTH COMMAND  /  DEEP SPACE PROGRAM"), Font(TEXT("Mono"), FMath::Max(8.f, S * 0.0085f), 220), Muted(0.9f));
	}

	void Hint(const FPainter& P, FVector2f Pos, const FString& Key, const FString& Label, float S, float& OutWidth)
	{
		const FSlateFontInfo KF = Font(TEXT("Bold"), FMath::Max(8.f, S * 0.0095f), 80);
		const FSlateFontInfo LF = Font(TEXT("Mono"), FMath::Max(8.f, S * 0.0092f), 160);
		const FVector2f KS = Measure(Key, KF);
		const FVector2f Pad(S * 0.006f, S * 0.003f);
		P.Frame(Pos, KS + Pad * 2.f, White(0.5f), Graphite(0.55f));
		P.Text(Pos + Pad, Key, KF, White(0.95f), 3);
		const FVector2f LS = Measure(Label, LF);
		P.Text(Pos + FVector2f(KS.X + Pad.X * 2.f + S * 0.006f, Pad.Y + (KS.Y - LS.Y) * 0.5f), Label, LF, Muted(1.f), 3);
		OutWidth = KS.X + Pad.X * 2.f + S * 0.006f + LS.X + S * 0.022f;
	}

	void Hints(const FPainter& P, FVector2f Pos, const TArray<TPair<FString, FString>>& Items, float S)
	{
		float X = Pos.X;
		for (const TPair<FString, FString>& I : Items)
		{
			float W = 0.f;
			Hint(P, FVector2f(X, Pos.Y), I.Key, I.Value, S, W);
			X += W;
		}
	}
}

int32 UOdysseySpaceHUDWidget::NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace OdysseyBrand;
	const int32 Layer = Super::NativePaint(Args, AllottedGeometry, MyCullingRect, OutDrawElements, LayerId, InWidgetStyle, bParentEnabled);
	const AOdysseySpacePlayerController* PC = Owner.Get();
	const AOdysseyTransitDirector* Dir = PC ? PC->GetDirector() : nullptr;
	if (!PC || !Dir)
	{
		return Layer;
	}
	const FVector2f Screen = FVector2f(AllottedGeometry.GetLocalSize());
	const float S = Screen.Y;  // layout unit: screen height
	FPainter P{OutDrawElements, AllottedGeometry, Layer + 1};
	const EOdysseySpaceFlow Flow = PC->GetFlow();
	const float FT = PC->GetFlowTime();
	if (Flow == EOdysseySpaceFlow::Intro)
	{
		return Layer;
	}

	const FOdysseyTransitTelemetry& Tel = Dir->GetTelemetry();
	const AOdysseyCelestialBody* Cur = Dir->GetBody(Dir->GetCurrentBody());
	const float In = Ramp(FT, 0.15f, 1.1f);

	// cinematic letterbox during transfers
	const float Bars = Dir->IsTraveling() ? Ramp(Tel.Progress * 20.f, 0.f, 1.f) * (1.f - Ramp(Tel.Progress, 0.97f, 1.f)) : 0.f;
	if (Bars > 0.f)
	{
		const float BH = S * 0.075f * Bars;
		P.Box(FVector2f(0, 0), FVector2f(Screen.X, BH), FLinearColor(0, 0, 0, 0.92f));
		P.Box(FVector2f(0, Screen.Y - BH), FVector2f(Screen.X, BH), FLinearColor(0, 0, 0, 0.92f));
	}

	Badge(P, S, Flow == EOdysseySpaceFlow::Menu ? In : 0.85f * In);

	const FSlateFontInfo Mono = Font(TEXT("Mono"), FMath::Max(8.f, S * 0.0105f), 200);
	const FSlateFontInfo MonoSmall = Font(TEXT("Mono"), FMath::Max(8.f, S * 0.0088f), 220);
	const FSlateFontInfo Label = Font(TEXT("Bold"), FMath::Max(10.f, S * 0.026f), 260);
	const FSlateFontInfo Body = Font(TEXT("Regular"), FMath::Max(9.f, S * 0.0125f), 40);
	const FSlateFontInfo Title = Font(TEXT("Bold"), FMath::Max(14.f, S * 0.05f), 520);

	if (Flow == EOdysseySpaceFlow::Menu)
	{
		const float X0 = S * 0.07f;
		float Y = S * 0.38f;
		P.Text(FVector2f(X0, Y - S * 0.045f), TEXT("MISSION SELECT"), MonoSmall, Ion(0.9f * In));
		P.Box(FVector2f(X0, Y - S * 0.02f), FVector2f(S * 0.32f * In, 1.f), White(0.18f));
		for (int32 i = 0; i < AOdysseySpacePlayerController::NumMenuItems; ++i)
		{
			const float ItemIn = Ramp(FT, 0.3f + i * 0.12f, 1.0f + i * 0.12f);
			const bool bSel = i == PC->GetMenuIndex();
			const float Shift = (bSel ? S * 0.012f : 0.f) + (1.f - ItemIn) * S * 0.03f;
			FPainter Q = P;
			Q.Opacity = ItemIn;
			if (bSel)
			{
				Q.Box(FVector2f(X0, Y + S * 0.004f), FVector2f(3.f, S * 0.056f), Ion(1.f));
				Q.Box(FVector2f(X0, Y + S * 0.004f), FVector2f(S * 0.36f, S * 0.056f), Graphite(0.45f));
			}
			Q.Text(FVector2f(X0 + Shift + S * 0.012f, Y + S * 0.006f), FString::Printf(TEXT("%02d"), i + 1), MonoSmall, bSel ? Ion(1.f) : Muted(0.7f), 2);
			Q.Text(FVector2f(X0 + Shift + S * 0.045f, Y), Upper(AOdysseySpacePlayerController::MenuLabel(i)), Label, bSel ? White(1.f) : White(0.55f), 2);
			Q.Text(FVector2f(X0 + Shift + S * 0.046f, Y + S * 0.038f), AOdysseySpacePlayerController::MenuDetail(i).ToString(), Body, bSel ? Muted(1.f) : Muted(0.5f), 2);
			Y += S * 0.082f;
		}
		Hints(P, FVector2f(X0, S * 0.9f), {{TEXT("W / S"), TEXT("SELECT")}, {TEXT("ENTER"), TEXT("CONFIRM")}}, S);
		if (Cur)
		{
			P.TextAligned(FVector2f(Screen.X - S * 0.05f, S * 0.93f), FVector2f(1.f, 0.f),
				FString::Printf(TEXT("%s  /  %s  /  PARKING ORBIT"), *Upper(Cur->DisplayName), *Upper(Cur->Designation)), MonoSmall, Muted(0.8f * In));
		}
	}

	if (Flow == EOdysseySpaceFlow::Navigation || Flow == EOdysseySpaceFlow::Descending)
	{
		const bool bTravel = Dir->IsTraveling();
		const bool bAligning = Tel.Phase == EOdysseyTransitPhase::Aligning;

		// transfer planner (hidden during the transfer itself)
		const float PanelA = bTravel ? 0.f : In;
		if (PanelA > 0.f)
		{
			FPainter Q = P;
			Q.Opacity = PanelA;
			const float W = S * 0.44f, RowH = S * 0.075f;
			const FVector2f Pos(Screen.X - W - S * 0.04f, S * 0.11f);
			const int32 N = Dir->NumBodies();
			const FVector2f Size(W, S * 0.09f + RowH * N + S * 0.09f);
			Q.Frame(Pos, Size, White(0.8f), Graphite(0.62f));
			Q.Text(Pos + FVector2f(S * 0.018f, S * 0.016f), TEXT("NAVIGATION  /  TRANSFER PLANNER"), MonoSmall, Ion(1.f), 3);
			Q.Text(Pos + FVector2f(S * 0.018f, S * 0.04f), TEXT("OTV-1 MERIDIAN  -  CREW TRANSIT VEHICLE"), MonoSmall, Muted(0.9f), 3);
			float Y = Pos.Y + S * 0.075f;
			for (int32 i = 0; i < N; ++i)
			{
				const AOdysseyCelestialBody* B = Dir->GetBody(i);
				if (!B) continue;
				const bool bCur = i == Dir->GetCurrentBody();
				const bool bSel = i == PC->GetSelectedBody();
				if (bSel)
				{
					Q.Box(FVector2f(Pos.X + 1.f, Y), FVector2f(W - 2.f, RowH - S * 0.006f), Ion(0.10f), 2);
					Q.Box(FVector2f(Pos.X + 1.f, Y), FVector2f(3.f, RowH - S * 0.006f), Ion(1.f), 3);
				}
				Q.Text(FVector2f(Pos.X + S * 0.02f, Y + S * 0.008f), FString::Printf(TEXT("%d"), i + 1), MonoSmall, Muted(0.8f), 4);
				Q.Text(FVector2f(Pos.X + S * 0.042f, Y + S * 0.002f), Upper(B->DisplayName), Font(TEXT("Bold"), FMath::Max(10.f, S * 0.021f), 220), White(bSel || bCur ? 1.f : 0.7f), 4);
				Q.Text(FVector2f(Pos.X + S * 0.043f, Y + S * 0.034f), Upper(B->Designation), MonoSmall, Muted(0.85f), 4);
				const FString Right = bCur ? FString(TEXT("CURRENT ORBIT")) :
					FString::Printf(TEXT("%s  /  %s"), *Km(Dir->RealDistanceKm(Dir->GetCurrentBody(), i)), *Duration(Dir->TransferHours(Dir->GetCurrentBody(), i)));
				Q.TextAligned(FVector2f(Pos.X + W - S * 0.018f, Y + S * 0.012f), FVector2f(1.f, 0.f), Right, MonoSmall, bCur ? Ion(1.f) : White(0.85f), 4);
				if (bCur)
				{
					Q.Diamond(FVector2f(Pos.X + W - S * 0.018f - Measure(Right, MonoSmall).X - S * 0.014f, Y + S * 0.019f), S * 0.0055f, Ion(1.f), 4);
				}
				Y += RowH;
			}
			if (const AOdysseyCelestialBody* SelB = Dir->GetBody(PC->GetSelectedBody()))
			{
				Q.Box(FVector2f(Pos.X + S * 0.018f, Y + S * 0.004f), FVector2f(W - S * 0.036f, 1.f), White(0.15f), 3);
				float LY = Y + S * 0.016f;
				for (const FString& Ln : Wrap(SelB->Summary.ToString(), Body, W - S * 0.036f))
				{
					Q.Text(FVector2f(Pos.X + S * 0.018f, LY), Ln, Body, Muted(1.f), 4);
					LY += S * 0.02f;
				}
			}
		}

		if (bAligning)
		{
			const float Pulse = 0.55f + 0.45f * FMath::Sin(FT * 5.f);
			P.TextAligned(FVector2f(Screen.X * 0.5f, S * 0.8f), FVector2f(0.5f, 0.f), PhaseName(Tel.Phase), Mono, Ion(Pulse));
		}

		if (bTravel)
		{
			// transfer telemetry
			const float W = S * 0.5f, H = S * 0.205f;
			const FVector2f Pos(S * 0.05f, Screen.Y - H - S * 0.11f);
			const AOdysseyCelestialBody* O = Dir->GetBody(Tel.Origin);
			const AOdysseyCelestialBody* T = Dir->GetBody(Tel.Target);
			P.Frame(Pos, FVector2f(W, H), White(0.8f), Graphite(0.6f));
			P.Text(Pos + FVector2f(S * 0.018f, S * 0.014f), FString::Printf(TEXT("TRANSFER  %s  >  %s"), O ? *Upper(O->DisplayName) : TEXT("-"), T ? *Upper(T->DisplayName) : TEXT("-")), MonoSmall, Muted(1.f), 3);
			const bool bBurn = Tel.Phase == EOdysseyTransitPhase::DepartureBurn || Tel.Phase == EOdysseyTransitPhase::ArrivalBurn;
			P.Text(Pos + FVector2f(S * 0.018f, S * 0.034f), PhaseName(Tel.Phase), Font(TEXT("Bold"), FMath::Max(10.f, S * 0.022f), 260), bBurn ? Amber(1.f) : Ion(1.f), 3);
			const FVector2f Bar = Pos + FVector2f(S * 0.018f, S * 0.072f);
			const float BW = W - S * 0.036f;
			P.Box(Bar, FVector2f(BW, 3.f), White(0.15f), 3);
			P.Box(Bar, FVector2f(BW * Tel.Progress, 3.f), Ion(1.f), 4);
			for (float Edge : {0.2f, 0.665f, 0.76f})
			{
				P.Box(Bar + FVector2f(BW * Edge - 0.5f, -3.f), FVector2f(1.f, 9.f), White(0.35f), 4);
			}
			const TArray<TPair<FString, FString>> Rows = {
				{TEXT("REL. VELOCITY"), FString::Printf(TEXT("%.2f KM/S"), Tel.VelocityKms)},
				{TEXT("DISTANCE TO GO"), Km(Tel.DistanceRemainingKm)},
				{TEXT("MISSION ELAPSED"), FString(TEXT("T+ ")) + Duration(Tel.MissionHours)},
				{TEXT("ARRIVAL IN"), Duration(FMath::Max(0.0, Tel.LegHours - Tel.MissionHours))}};
			for (int32 i = 0; i < Rows.Num(); ++i)
			{
				const float CX = Pos.X + S * 0.018f + (i % 2) * (W * 0.5f);
				const float CY = Pos.Y + S * 0.092f + (i / 2) * S * 0.052f;
				P.Text(FVector2f(CX, CY), Rows[i].Key, MonoSmall, Muted(0.9f), 3);
				P.Text(FVector2f(CX, CY + S * 0.017f), Rows[i].Value, Font(TEXT("Bold"), FMath::Max(10.f, S * 0.018f), 120), White(1.f), 3);
			}
			P.TextAligned(FVector2f(Screen.X - S * 0.05f, Screen.Y - S * 0.105f - S * 0.03f), FVector2f(1.f, 0.f), TEXT("OTV-1 MERIDIAN  /  CREW 4  /  NOMINAL"), MonoSmall, Muted(0.85f));
		}
		else if (!bAligning)
		{
			TArray<TPair<FString, FString>> Items = {{TEXT("A / D"), TEXT("DESTINATION")}, {TEXT("ENTER"), TEXT("LAUNCH TRANSFER")}, {TEXT("C"), TEXT("CAMERA")}};
			if (Cur && Cur->BodyId == FName(TEXT("earth")))
			{
				Items.Add({TEXT("E"), TEXT("DESCEND TO EARTH COMMAND")});
			}
			Items.Add({TEXT("ESC"), TEXT("MENU")});
			Hints(P, FVector2f(S * 0.05f, S * 0.92f), Items, S);
		}

		// arrival banner
		const float SA = Dir->SinceArrival();
		if (!bTravel && Cur && SA < 7.f)
		{
			const float A = Ramp(SA, 0.3f, 1.3f) * (1.f - Ramp(SA, 5.5f, 7.f));
			FPainter Q = P;
			Q.Opacity = A;
			const FVector2f C(Screen.X * 0.5f, S * 0.12f);
			Q.TextAligned(C, FVector2f(0.5f, 0.f), TEXT("ORBIT ESTABLISHED"), MonoSmall, Ion(1.f), 3);
			Q.TextAligned(C + FVector2f(0, S * 0.025f), FVector2f(0.5f, 0.f), Upper(Cur->DisplayName), Title, White(1.f), 3);
			Q.TextAligned(C + FVector2f(0, S * 0.1f), FVector2f(0.5f, 0.f), Upper(Cur->Designation), MonoSmall, Muted(1.f), 3);
		}
	}

	// fade to black (descend)
	const float Fade = PC->GetFadeToBlack();
	if (Fade > 0.f)
	{
		P.Box(FVector2f(0, 0), Screen, FLinearColor(0, 0, 0, Fade), 20);
		P.TextAligned(Screen * 0.5f, FVector2f(0.5f, 0.5f), TEXT("DESCENDING TO EARTH COMMAND"), Mono, Ion(Fade), 21);
	}
	return Layer + 30;
}
