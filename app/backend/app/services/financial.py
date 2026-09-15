from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


MONEY = Decimal("0.01")
PERCENT = Decimal("0.01")


@dataclass(frozen=True)
class FinancialMetrics:
    roi_percent: Decimal | None
    npv: Decimal | None
    irr_percent: Decimal | None
    payback_years: Decimal | None
    missing_data: list[str]

    def as_dict(self) -> dict[str, str | list[str] | None]:
        return {
            "roi_percent": str(self.roi_percent) if self.roi_percent is not None else None,
            "npv": str(self.npv) if self.npv is not None else None,
            "irr_percent": str(self.irr_percent) if self.irr_percent is not None else None,
            "payback_years": str(self.payback_years) if self.payback_years is not None else None,
            "missing_data": self.missing_data,
        }


class FinancialEngine:
    def calculate(
        self,
        initial_investment: Decimal,
        annual_costs: list[Decimal],
        annual_benefits: list[Decimal],
        discount_rate_percent: Decimal,
    ) -> FinancialMetrics:
        if not annual_costs or not annual_benefits or len(annual_costs) != len(annual_benefits):
            return FinancialMetrics(None, None, None, None, ["annual_costs_and_benefits_for_each_period"])
        net_flows = [benefit - cost for benefit, cost in zip(annual_benefits, annual_costs, strict=True)]
        missing: list[str] = []
        roi = None
        if initial_investment > 0:
            roi = ((sum(net_flows) - initial_investment) / initial_investment * 100).quantize(PERCENT, rounding=ROUND_HALF_UP)
        else:
            missing.append("initial_investment_for_roi")
        rate = discount_rate_percent / 100
        npv = (-initial_investment + sum(flow / ((Decimal(1) + rate) ** period) for period, flow in enumerate(net_flows, 1))).quantize(MONEY, rounding=ROUND_HALF_UP)
        irr = self._irr(initial_investment, net_flows)
        payback = self._payback(initial_investment, net_flows)
        if irr is None:
            missing.append("cash_flows_with_an_irr_solution")
        if payback is None:
            missing.append("positive_cumulative_cash_flow_for_payback")
        return FinancialMetrics(roi, npv, irr, payback, missing)

    @staticmethod
    def _irr(initial: Decimal, flows: list[Decimal]) -> Decimal | None:
        def value(rate: Decimal) -> Decimal:
            return -initial + sum(flow / ((Decimal(1) + rate) ** period) for period, flow in enumerate(flows, 1))
        low, high = Decimal("-0.99"), Decimal("10")
        if value(low) * value(high) > 0:
            return None
        for _ in range(160):
            middle = (low + high) / 2
            if value(middle) > 0:
                low = middle
            else:
                high = middle
        return (((low + high) / 2) * 100).quantize(PERCENT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _payback(initial: Decimal, flows: list[Decimal]) -> Decimal | None:
        if initial == 0:
            return Decimal("0.00")
        cumulative = Decimal(0)
        for period, flow in enumerate(flows, 1):
            previous = cumulative
            cumulative += flow
            if cumulative >= initial and flow > 0:
                fraction = (initial - previous) / flow
                return (Decimal(period - 1) + fraction).quantize(PERCENT, rounding=ROUND_HALF_UP)
        return None
