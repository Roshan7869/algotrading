from datetime import datetime
from math import exp

from pandas import DataFrame

from freqtrade.constants import Config
from freqtrade.optimize.hyperopt import IHyperOptLoss


class DrawdownAwareLoss(IHyperOptLoss):
    @staticmethod
    def hyperopt_loss_function(
        results: DataFrame,
        trade_count: int,
        min_date: datetime,
        max_date: datetime,
        config: Config,
        processed: dict[str, DataFrame],
        *args,
        **kwargs,
    ) -> float:
        total_profit = results["profit_ratio"].sum()
        trade_duration = results["trade_duration"].mean()

        winning_trades = results[results["profit_ratio"] > 0]
        losing_trades = results[results["profit_ratio"] < 0]
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = win_count / max(trade_count, 1)

        avg_win = winning_trades["profit_ratio"].mean() if win_count > 0 else 0
        avg_loss = losing_trades["profit_ratio"].mean() if loss_count > 0 else 0

        profit_factor = abs(avg_win * win_count / max(avg_loss * loss_count, 0.0001))

        # Max drawdown from equity curve
        if "profit_ratio" in results.columns and len(results) > 1:
            cumulative = results["profit_ratio"].cumsum()
            peak = cumulative.cummax()
            drawdown = (peak - cumulative).max()
        else:
            drawdown = 0

        # Penalize: negative profit, high drawdown, low profit factor, low win rate
        profit_score = max(0, 1 - total_profit / 3.0) if total_profit < 0 else 0
        drawdown_score = min(drawdown / 0.5, 2.0)
        pf_score = max(0, 1 - profit_factor / 1.5) if profit_factor < 1.5 else 0
        wr_score = max(0, 0.5 - win_rate) if win_rate < 0.5 else 0

        min_trades = max(0, 1 - trade_count / 30)
        duration_score = min(trade_duration / 600, 1) * 0.2

        return profit_score + drawdown_score + pf_score + wr_score + min_trades + duration_score
