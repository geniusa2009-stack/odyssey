#include "OdysseyLogoWidget.h"

#include "HAL/PlatformTime.h"
#include "OdysseyBrandPaint.h"

namespace
{
	float Ramp(float T, float A, float B)
	{
		const float X = FMath::Clamp((T - A) / (B - A), 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}

	float EaseOut(float T, float A, float B)
	{
		const float X = FMath::Clamp((T - A) / (B - A), 0.f, 1.f);
		return 1.f - FMath::Pow(1.f - X, 3.f);
	}

	float Overshoot(float T, float A, float B)
	{
		const float X = FMath::Clamp((T - A) / (B - A), 0.f, 1.f);
		const float S = 1.9f;
		const float Y = X - 1.f;
		return 1.f + (S + 1.f) * Y * Y * Y + S * Y * Y;
	}

	struct FTimeline
	{
		float Scan0, Scan1, Mark0, Mark1, Core0, Core1, Word0, Word1, Track1, Sweep0, Sweep1, Sub0, Sub1, Out0, Out1, Bg0, Bg1, Total;
	};

	const FTimeline& Timeline(EOdysseyLogoStyle S)
	{
		static const FTimeline Intro = {0.2f, 1.6f, 0.55f, 1.55f, 1.35f, 1.8f, 1.25f, 2.95f, 3.3f, 3.05f, 3.85f, 3.25f, 4.25f, 5.45f, 6.35f, 5.4f, 6.7f, 6.8f};
		static const FTimeline Sting = {0.0f, 0.6f, 0.05f, 0.55f, 0.45f, 0.75f, 0.25f, 1.2f, 1.4f, 1.2f, 1.75f, 1.2f, 1.8f, 2.6f, 3.1f, 0.f, 0.f, 3.2f};
		return S == EOdysseyLogoStyle::Intro ? Intro : Sting;
	}
}

void UOdysseyLogoWidget::Play(EOdysseyLogoStyle InStyle)
{
	Style = InStyle;
	StartTime = FPlatformTime::Seconds();
	TimeOffset = 0.0;
	bPlayed = true;
	SetVisibility(ESlateVisibility::HitTestInvisible);
}

void UOdysseyLogoWidget::Skip()
{
	const FTimeline& L = Timeline(Style);
	if (GetElapsed() < L.Out0)
	{
		TimeOffset += L.Out0 - GetElapsed();
	}
}

float UOdysseyLogoWidget::GetElapsed() const
{
	return bPlayed ? (float)(FPlatformTime::Seconds() - StartTime + TimeOffset) : 0.f;
}

float UOdysseyLogoWidget::GetDuration() const
{
	return Timeline(Style).Total;
}

float UOdysseyLogoWidget::GetSceneReveal() const
{
	if (Style != EOdysseyLogoStyle::Intro)
	{
		return 1.f;
	}
	const FTimeline& L = Timeline(Style);
	return Ramp(GetElapsed(), L.Bg0, L.Bg1);
}

int32 UOdysseyLogoWidget::NativePaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	int32 Layer = Super::NativePaint(Args, AllottedGeometry, MyCullingRect, OutDrawElements, LayerId, InWidgetStyle, bParentEnabled);
	if (!bPlayed)
	{
		if (bHoldBlack)
		{
			OdysseyBrand::FPainter Hold{OutDrawElements, AllottedGeometry, Layer + 1};
			Hold.Box(FVector2f(0, 0), FVector2f(AllottedGeometry.GetLocalSize()), FLinearColor(0.004f, 0.006f, 0.009f, 1.f));
			return Layer + 2;
		}
		return Layer;
	}
	if (IsFinished())
	{
		return Layer;
	}
	using namespace OdysseyBrand;
	const FTimeline& L = Timeline(Style);
	const float T = GetElapsed();
	const FVector2f Screen = FVector2f(AllottedGeometry.GetLocalSize());
	FPainter P{OutDrawElements, AllottedGeometry, Layer + 1};

	// black open (intro only)
	if (Style == EOdysseyLogoStyle::Intro)
	{
		const float Bg = 1.f - Ramp(T, L.Bg0, L.Bg1);
		P.Box(FVector2f(0, 0), Screen, FLinearColor(0.004f, 0.006f, 0.009f, Bg));
	}

	const float Fade = 1.f - Ramp(T, L.Out0, L.Out1);
	P.Opacity = Fade;
	P.Layer = Layer + 4;

	// lockup geometry: [mark]  ODYSSEY / subtitle, centred
	const float H = Screen.Y * (Style == EOdysseyLogoStyle::Intro ? 0.082f : 0.06f);
	const float Track = FMath::Lerp(0.95f, 0.2f, EaseOut(T, L.Word0, L.Track1));
	const float WordW = WordmarkWidth(H, Track);
	const float FinalWordW = WordmarkWidth(H, 0.2f);
	const float MarkSize = H * 1.32f;
	const float Gap = H * 0.62f;
	const float LockW = MarkSize + Gap + FinalWordW;
	const FVector2f C = Screen * 0.5f - FVector2f(0.f, H * 0.25f);
	const float Left = C.X - LockW * 0.5f;
	const FVector2f MarkCenter(Left + MarkSize * 0.5f, C.Y);
	const FVector2f WordTL(Left + MarkSize + Gap + (FinalWordW - WordW) * 0.5f, C.Y - H * 0.5f);
	const float Stroke = FMath::Max(2.f, H * 0.105f);

	// scan line
	{
		const float Grow = EaseOut(T, L.Scan0, L.Scan0 + (L.Scan1 - L.Scan0) * 0.55f);
		const float Shrink = Ramp(T, L.Scan0 + (L.Scan1 - L.Scan0) * 0.55f, L.Scan1);
		const float W = FMath::Lerp(Screen.X * 0.56f * Grow, LockW * 1.08f, Shrink);
		const float A = Ramp(T, L.Scan0, L.Scan0 + 0.25f) * (1.f - Ramp(T, L.Scan1, L.Scan1 + 0.6f));
		const float Y = C.Y + H * 0.95f;
		P.Box(FVector2f(C.X - W * 0.5f, Y - 3.f), FVector2f(W, 6.f), Ion(0.10f * A));
		P.Box(FVector2f(C.X - W * 0.5f, Y - 0.75f), FVector2f(W, 1.5f), Ion(0.9f * A));
	}

	// mark
	{
		const float Reveal = Ramp(T, L.Mark0, L.Mark1);
		const float Core = T < L.Core0 ? 0.f : Overshoot(T, L.Core0, L.Core1);
		const float Breath = 0.85f + 0.15f * FMath::Sin(T * 2.4f);
		OdysseyBrand::Mark(P, MarkCenter, MarkSize, Reveal, Core, Ion(1.f), Stroke * 0.8f);
		if (Core > 0.f)
		{
			P.Diamond(MarkCenter, MarkSize * 0.62f, Ion(0.06f * Breath), -1);
		}
	}

	// wordmark: soft ion glow under crisp white strokes
	{
		const float Reveal = Ramp(T, L.Word0, L.Word1);
		Wordmark(P, WordTL, H, Track, Reveal, Ion(0.16f), Stroke * 2.6f);
		Wordmark(P, WordTL, H, Track, Reveal, White(1.f), Stroke);
	}

	// light sweep across the lockup
	if (T > L.Sweep0 && T < L.Sweep1)
	{
		const float X = FMath::Lerp(Left - H, Left + LockW + H, Ramp(T, L.Sweep0, L.Sweep1));
		const float A = FMath::Sin(Ramp(T, L.Sweep0, L.Sweep1) * PI);
		for (int32 i = 0; i < 5; ++i)
		{
			const float W = H * (0.12f + 0.16f * i);
			P.Box(FVector2f(X - W * 0.5f, C.Y - H * 0.75f), FVector2f(W, H * 1.5f), Ion(0.05f * A), 3);
		}
	}

	// subtitle typewriter + rules
	{
		const FSlateFontInfo Mono = Font(TEXT("Mono"), FMath::Max(9.f, H * 0.2f), 260);
		const int32 N = FMath::RoundToInt(Subtitle.Len() * Ramp(T, L.Sub0, L.Sub1));
		const FString Shown = Subtitle.Left(N) + ((N < Subtitle.Len() && N > 0 && FMath::Fmod(T * 6.f, 1.f) < 0.5f) ? TEXT("_") : TEXT(""));
		const FVector2f SubAnchor(C.X, C.Y + H * 1.25f);
		const FVector2f Full = Measure(Subtitle, Mono);
		P.Text(SubAnchor - FVector2f(Full.X * 0.5f, 0.f), Shown, Mono, Muted(0.95f));
		const float Rule = Ramp(T, L.Sub0 + 0.2f, L.Sub1) * H * 2.2f;
		const float RY = SubAnchor.Y + Full.Y * 0.55f;
		if (Rule > 1.f)
		{
			P.Lines({FVector2f(C.X - Full.X * 0.5f - H * 0.35f - Rule, RY), FVector2f(C.X - Full.X * 0.5f - H * 0.35f, RY)}, Ion(0.7f), 1.2f);
			P.Lines({FVector2f(C.X + Full.X * 0.5f + H * 0.35f, RY), FVector2f(C.X + Full.X * 0.5f + H * 0.35f + Rule, RY)}, Ion(0.7f), 1.2f);
		}
	}
	return Layer + 12;
}
