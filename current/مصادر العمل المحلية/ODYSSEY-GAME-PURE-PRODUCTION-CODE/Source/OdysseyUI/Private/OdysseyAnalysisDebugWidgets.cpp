
#include "OdysseyAnalysisDebugWidgets.h"

#include "Components/TextBlock.h"
#include "Fonts/SlateFontInfo.h"
#include "OdysseyBackendSubsystem.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"


void UOdysseyFutureLensDebugWidget::NativeConstruct()
{
	Super::NativeConstruct();
	if (UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this))
	{
		B->OnFutureLensReady.AddDynamic(this, &UOdysseyFutureLensDebugWidget::ShowLens);
	}
}

FString UOdysseyFutureLensDebugWidget::Describe(const FOdysseyFutureLensView& V)
{
	if (!V.bOk)
	{
		return TEXT("Future Lens: response not usable");
	}
	FString S = FString::Printf(TEXT("FUTURE LENS  mode=%s  base tick %lld  horizon %.1f h\n"), *V.PredictionMode.ToString(), V.BaseTick, V.HorizonHours);
	for (const FOdysseyLensBranchView& B : V.Branches)
	{
		S += FString::Printf(TEXT("\n[%s] %s %s%s"), *B.Id.ToString(), *B.Action.ToString(), *B.Target.ToString(), B.bBaseline ? TEXT("  (baseline)") : TEXT(""));
		if (!B.bValid)
		{
			S += FString::Printf(TEXT("\n   not possible now: %s"), *B.RejectionReason.ToString());
			continue;
		}
		S += FString::Printf(TEXT("\n   outcome %s · confidence %s · peak risk %.2f"), *B.ProjectedOutcomeTier.ToString(), *B.ConfidenceLevel.ToString(), B.RiskPeak);
		for (const FString& H : B.WorldHints) S += TEXT("\n   ") + H;
		for (const FName& W : B.Warnings) S += TEXT("\n   ! ") + W.ToString();
	}
	return S;
}

void UOdysseyFutureLensDebugWidget::ShowLens(const FOdysseyFutureLensView& View)
{
	if (Body)
	{
		Body->SetText(FText::FromString(Describe(View)));
	}
}


void UOdysseyBlackBoxDebugWidget::NativeConstruct()
{
	Super::NativeConstruct();
	if (UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this))
	{
		B->OnBlackBoxReady.AddDynamic(this, &UOdysseyBlackBoxDebugWidget::ShowBlackBox);
	}
}

void UOdysseyBlackBoxDebugWidget::ShowBlackBox(const FOdysseyBlackBoxView& View)
{
	Graph = View;
	if (Header)
	{
		Header->SetText(FText::FromString(FString::Printf(TEXT("BLACK BOX  %s  %s  — %s  (%d nodes, %d edges)"), *View.MissionId.ToString(),
			*View.OutcomeTier.ToString(), *View.Statement, View.Nodes.Num(), View.Edges.Num())));
	}
	Invalidate(EInvalidateWidgetReason::Paint);
}

int32 UOdysseyBlackBoxDebugWidget::NativePaint(const FPaintArgs& Args, const FGeometry& Geo, const FSlateRect& Cull,
	FSlateWindowElementList& Out, int32 LayerId, const FWidgetStyle& Style, bool bParentEnabled) const
{
	const int32 Base = Super::NativePaint(Args, Geo, Cull, Out, LayerId, Style, bParentEnabled);
	if (Graph.Nodes.Num() == 0)
	{
		return Base;
	}
	
	const FVector2D Size = Geo.GetLocalSize();
	TMap<int64, int32> ColumnOf;
	TArray<int64> Ticks;
	for (const FOdysseyCausalNodeView& N : Graph.Nodes) Ticks.AddUnique(N.SimTick);
	Ticks.Sort();
	for (int32 I = 0; I < Ticks.Num(); ++I) ColumnOf.Add(Ticks[I], I);
	TMap<int32, int32> RowsInColumn;
	TMap<FName, FVector2D> Pos;
	const float ColW = Size.X / FMath::Max(1, Ticks.Num());
	for (const FOdysseyCausalNodeView& N : Graph.Nodes)
	{
		const int32 Col = ColumnOf[N.SimTick];
		const int32 Row = RowsInColumn.FindOrAdd(Col)++;
		Pos.Add(N.Id, FVector2D(ColW * (Col + 0.5f), 40.f + Row * 46.f));
	}
	const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle("Regular", 8);
	for (const FOdysseyCausalEdgeView& E : Graph.Edges)
	{
		const FVector2D* A = Pos.Find(E.Source);
		const FVector2D* B = Pos.Find(E.Target);
		if (A && B)
		{
			TArray<FVector2D> Line{*A, *B};
			FSlateDrawElement::MakeLines(Out, Base + 1, Geo.ToPaintGeometry(), Line, ESlateDrawEffect::None, FLinearColor(0.4f, 0.7f, 1.f, 0.6f), true, 1.5f);
		}
	}
	for (const FOdysseyCausalNodeView& N : Graph.Nodes)
	{
		const FVector2D P = Pos[N.Id];
		const FLinearColor C = N.Type == TEXT("decision") ? FLinearColor(1.f, 0.8f, 0.3f) : N.Severity == TEXT("critical") ? FLinearColor(1.f, 0.35f, 0.3f) : FLinearColor(0.85f, 0.9f, 1.f);
		FSlateDrawElement::MakeBox(Out, Base + 2, Geo.ToPaintGeometry(FVector2f(10.f, 10.f), FSlateLayoutTransform(FVector2f(P - FVector2D(5.f, 5.f)))),
			FCoreStyle::Get().GetBrush("WhiteBrush"), ESlateDrawEffect::None, C);
		FSlateDrawElement::MakeText(Out, Base + 3, Geo.ToPaintGeometry(FVector2f(ColW, 16.f), FSlateLayoutTransform(FVector2f(P + FVector2D(-ColW * 0.45f, 8.f)))),
			N.Label.Left(36), Font, ESlateDrawEffect::None, C);
	}
	return Base + 3;
}
