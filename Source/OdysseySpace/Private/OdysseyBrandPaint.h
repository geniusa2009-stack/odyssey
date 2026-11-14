// ODYSSEY brand drawing kit for code-drawn Slate UI: palette, the geometric ODYSSEY wordmark
// (stroked, chamfered glyphs that can "draw on"), the diamond mark, panels, rules and text.
#pragma once

#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"
#include "Layout/Geometry.h"
#include "Rendering/DrawElements.h"

namespace OdysseyBrand
{
	FLinearColor Ion(float A = 1.f);
	FLinearColor IonDeep(float A = 1.f);
	FLinearColor White(float A = 1.f);
	FLinearColor Muted(float A = 1.f);
	FLinearColor Graphite(float A = 1.f);
	FLinearColor Amber(float A = 1.f);
	FLinearColor Red(float A = 1.f);

	FSlateFontInfo Font(const TCHAR* Typeface, float Size, int32 LetterSpacing = 0);
	FVector2f Measure(const FString& Text, const FSlateFontInfo& FontInfo);

	struct FPainter
	{
		FSlateWindowElementList& List;
		const FGeometry& Geo;
		int32 Layer;
		float Opacity = 1.f;

		void Lines(const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, int32 LayerOffset = 0) const;
		void Box(FVector2f Pos, FVector2f Size, const FLinearColor& Color, int32 LayerOffset = 0) const;
		void Diamond(FVector2f Center, float HalfDiagonal, const FLinearColor& Color, int32 LayerOffset = 0) const;
		void Text(FVector2f Pos, const FString& Text, const FSlateFontInfo& FontInfo, const FLinearColor& Color, int32 LayerOffset = 0) const;
		// Text anchored by alignment (0 = left/top, 0.5 = centre, 1 = right/bottom).
		void TextAligned(FVector2f Anchor, FVector2f Align, const FString& Text, const FSlateFontInfo& FontInfo, const FLinearColor& Color, int32 LayerOffset = 0) const;
		// Thin frame with ion corner ticks (panel chrome).
		void Frame(FVector2f Pos, FVector2f Size, const FLinearColor& Line, const FLinearColor& Fill, int32 LayerOffset = 0) const;
	};

	// Width of the wordmark at cap height H with extra tracking (fraction of H).
	float WordmarkWidth(float H, float Tracking);
	// Draws "ODYSSEY". Reveal 0..1 draws the strokes on, letter by letter.
	void Wordmark(const FPainter& P, FVector2f TopLeft, float H, float Tracking, float Reveal, const FLinearColor& Color, float Thickness);
	// Diamond mark: outer outline (drawn on by Reveal) + filled inner diamond (scaled by Core).
	void Mark(const FPainter& P, FVector2f Center, float Size, float Reveal, float Core, const FLinearColor& LineColor, float Thickness);
}
