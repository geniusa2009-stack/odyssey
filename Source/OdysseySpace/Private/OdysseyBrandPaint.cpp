#include "OdysseyBrandPaint.h"

#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

namespace OdysseyBrand
{
	namespace
	{
		FLinearColor Srgb(uint8 R, uint8 G, uint8 B, float A)
		{
			FLinearColor C = FLinearColor::FromSRGBColor(FColor(R, G, B));
			C.A = A;
			return C;
		}

		// Glyph strokes in cap-height units (x right, y down). Chamfered, squared aerospace forms.
		struct FGlyph
		{
			float Width;
			TArray<TArray<FVector2f>> Strokes;
		};

		const TArray<FGlyph>& Glyphs()
		{
			static TArray<FGlyph> G;
			if (G.Num() == 0)
			{
				const float C = 0.17f;
				// O
				G.Add({0.84f, {{{C, 0}, {0.84f - C, 0}, {0.84f, C}, {0.84f, 1 - C}, {0.84f - C, 1}, {C, 1}, {0, 1 - C}, {0, C}, {C, 0}}}});
				// D
				G.Add({0.80f, {{{0, 0}, {0.80f - 0.22f, 0}, {0.80f, 0.22f}, {0.80f, 0.78f}, {0.80f - 0.22f, 1}, {0, 1}, {0, 0}}}});
				// Y
				G.Add({0.82f, {{{0, 0}, {0, 0.26f}, {0.17f, 0.47f}, {0.41f, 0.47f}},
				               {{0.82f, 0}, {0.82f, 0.26f}, {0.65f, 0.47f}, {0.41f, 0.47f}},
				               {{0.41f, 0.47f}, {0.41f, 1}}}});
				// S
				const TArray<FVector2f> S = {{0.78f, 0}, {C, 0}, {0, C}, {0, 0.36f}, {0.11f, 0.5f}, {0.67f, 0.5f}, {0.78f, 0.64f}, {0.78f, 1 - C}, {0.78f - C, 1}, {0, 1}};
				G.Add({0.78f, {S}});
				G.Add({0.78f, {S}});
				// E
				G.Add({0.70f, {{{0.70f, 0}, {0, 0}, {0, 1}, {0.70f, 1}}, {{0, 0.5f}, {0.56f, 0.5f}}}});
				// Y (copied first: adding an element of the array to itself is not allowed)
				const FGlyph Y = G[2];
				G.Add(Y);
			}
			return G;
		}

		float PolyLength(const TArray<FVector2f>& Pts)
		{
			float L = 0.f;
			for (int32 i = 1; i < Pts.Num(); ++i) L += FVector2f::Distance(Pts[i - 1], Pts[i]);
			return L;
		}

		// First Fraction of a polyline (by length).
		TArray<FVector2f> PartialPoly(const TArray<FVector2f>& Pts, float Fraction)
		{
			TArray<FVector2f> Out;
			if (Pts.Num() < 2 || Fraction <= 0.f) return Out;
			const float Total = PolyLength(Pts);
			float Want = Total * FMath::Clamp(Fraction, 0.f, 1.f);
			Out.Add(Pts[0]);
			for (int32 i = 1; i < Pts.Num() && Want > 0.f; ++i)
			{
				const float Seg = FVector2f::Distance(Pts[i - 1], Pts[i]);
				if (Seg <= Want)
				{
					Out.Add(Pts[i]);
					Want -= Seg;
				}
				else
				{
					Out.Add(FMath::Lerp(Pts[i - 1], Pts[i], Want / FMath::Max(Seg, 1e-4f)));
					Want = 0.f;
				}
			}
			return Out;
		}

		constexpr float LetterGap = 0.24f;
	}

	FLinearColor Ion(float A) { return Srgb(0x61, 0xBE, 0xD2, A); }
	FLinearColor IonDeep(float A) { return Srgb(0x1E, 0x5F, 0x74, A); }
	FLinearColor White(float A) { return Srgb(0xEE, 0xF1, 0xF2, A); }
	FLinearColor Muted(float A) { return Srgb(0x8E, 0x97, 0xA0, A); }
	FLinearColor Graphite(float A) { return Srgb(0x14, 0x18, 0x1D, A); }
	FLinearColor Amber(float A) { return Srgb(0xD6, 0x9A, 0x35, A); }
	FLinearColor Red(float A) { return Srgb(0xB8, 0x47, 0x43, A); }

	FSlateFontInfo Font(const TCHAR* Typeface, float Size, int32 LetterSpacing)
	{
		FSlateFontInfo F = FCoreStyle::GetDefaultFontStyle(FName(Typeface), Size);
		F.LetterSpacing = LetterSpacing;
		return F;
	}

	FVector2f Measure(const FString& Text, const FSlateFontInfo& FontInfo)
	{
		if (FSlateApplication::IsInitialized() && FSlateApplication::Get().GetRenderer())
		{
			const auto S = FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Text, FontInfo);
			return FVector2f((float)S.X, (float)S.Y);
		}
		return FVector2f(Text.Len() * FontInfo.Size * 0.62f, FontInfo.Size * 1.3f);
	}

	void FPainter::Lines(const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, int32 LayerOffset) const
	{
		if (Points.Num() < 2) return;
		FLinearColor C = Color;
		C.A *= Opacity;
		FSlateDrawElement::MakeLines(List, Layer + LayerOffset, Geo.ToPaintGeometry(), Points, ESlateDrawEffect::None, C, true, Thickness);
	}

	void FPainter::Box(FVector2f Pos, FVector2f Size, const FLinearColor& Color, int32 LayerOffset) const
	{
		FLinearColor C = Color;
		C.A *= Opacity;
		FSlateDrawElement::MakeBox(List, Layer + LayerOffset, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)),
			FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")), ESlateDrawEffect::None, C);
	}

	void FPainter::Diamond(FVector2f Center, float HalfDiagonal, const FLinearColor& Color, int32 LayerOffset) const
	{
		const float Side = HalfDiagonal * UE_SQRT_2;
		FLinearColor C = Color;
		C.A *= Opacity;
		const FVector2f Size(Side, Side);
		FSlateDrawElement::MakeBox(List, Layer + LayerOffset,
			Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Center - Size * 0.5f), FSlateRenderTransform(FQuat2f(FMath::DegreesToRadians(45.f))), FVector2f(0.5f, 0.5f)),
			FCoreStyle::Get().GetBrush(TEXT("WhiteBrush")), ESlateDrawEffect::None, C);
	}

	void FPainter::Text(FVector2f Pos, const FString& InText, const FSlateFontInfo& FontInfo, const FLinearColor& Color, int32 LayerOffset) const
	{
		FLinearColor C = Color;
		C.A *= Opacity;
		const FVector2f Size = Measure(InText, FontInfo) + FVector2f(4.f, 2.f);
		FSlateDrawElement::MakeText(List, Layer + LayerOffset, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), InText, FontInfo, ESlateDrawEffect::None, C);
	}

	void FPainter::TextAligned(FVector2f Anchor, FVector2f Align, const FString& InText, const FSlateFontInfo& FontInfo, const FLinearColor& Color, int32 LayerOffset) const
	{
		const FVector2f Size = Measure(InText, FontInfo);
		Text(Anchor - Size * Align, InText, FontInfo, Color, LayerOffset);
	}

	void FPainter::Frame(FVector2f Pos, FVector2f Size, const FLinearColor& Line, const FLinearColor& Fill, int32 LayerOffset) const
	{
		Box(Pos, Size, Fill, LayerOffset);
		const FVector2f A = Pos, B = Pos + FVector2f(Size.X, 0), C = Pos + Size, D = Pos + FVector2f(0, Size.Y);
		Lines({A, B, C, D, A}, Line * FLinearColor(1, 1, 1, 0.35f), 1.f, LayerOffset + 1);
		const float T = FMath::Min(14.f, Size.Y * 0.3f);
		const FLinearColor Tick = Ion(Line.A);
		Lines({A + FVector2f(0, T), A, A + FVector2f(T, 0)}, Tick, 2.f, LayerOffset + 2);
		Lines({C - FVector2f(0, T), C, C - FVector2f(T, 0)}, Tick, 2.f, LayerOffset + 2);
	}

	float WordmarkWidth(float H, float Tracking)
	{
		float W = 0.f;
		const TArray<FGlyph>& G = Glyphs();
		for (int32 i = 0; i < G.Num(); ++i)
		{
			W += G[i].Width * H + (i + 1 < G.Num() ? (LetterGap + Tracking) * H : 0.f);
		}
		return W;
	}

	void Wordmark(const FPainter& P, FVector2f TopLeft, float H, float Tracking, float Reveal, const FLinearColor& Color, float Thickness)
	{
		const TArray<FGlyph>& G = Glyphs();
		float X = TopLeft.X;
		const int32 N = G.Num();
		for (int32 i = 0; i < N; ++i)
		{
			// staggered draw-on: each letter starts a little after the previous one
			const float LetterReveal = FMath::Clamp((Reveal * (N + 1.5f) - i * 1.0f) / 2.5f, 0.f, 1.f);
			if (LetterReveal > 0.f)
			{
				for (const TArray<FVector2f>& Stroke : G[i].Strokes)
				{
					TArray<FVector2f> Pts;
					for (const FVector2f& Q : Stroke)
					{
						Pts.Add(FVector2f(X + Q.X * H, TopLeft.Y + Q.Y * H));
					}
					P.Lines(PartialPoly(Pts, LetterReveal), Color, Thickness, 1);
				}
			}
			X += G[i].Width * H + (LetterGap + Tracking) * H;
		}
	}

	void Mark(const FPainter& P, FVector2f Center, float Size, float Reveal, float Core, const FLinearColor& LineColor, float Thickness)
	{
		const float R = Size * 0.5f;
		const TArray<FVector2f> Outline = {Center + FVector2f(0, -R), Center + FVector2f(R, 0), Center + FVector2f(0, R), Center + FVector2f(-R, 0), Center + FVector2f(0, -R)};
		P.Lines(PartialPoly(Outline, Reveal), LineColor, Thickness, 1);
		if (Core > 0.f)
		{
			FLinearColor Glow = LineColor;
			Glow.A *= 0.18f;
			P.Diamond(Center, R * 0.62f * Core, Glow, 0);
			P.Diamond(Center, R * 0.36f * Core, LineColor, 2);
		}
	}
}
