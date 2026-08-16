use std::collections::HashMap;
use std::ops::RangeInclusive;

use crate::chart::{Basis, Message, ViewState};
use crate::connector::fetcher::FetchRange;

use data::chart::indicator::{IndicatorConfig, IndicatorConfigs, KlineIndicator};
use data::chart::kline::KlineDataPoint;
use data::chart::{BasisSeries, PlotData};
use exchange::adapter::Exchange;
use exchange::{Kline, Timeframe, Trade, UnixMs};

use iced::widget::canvas::Frame;
use iced::Theme;

use super::plot::AnySeries;

pub mod cumulative_delta;
pub mod open_interest;
pub mod volume;
pub mod rsi;
pub mod macd;
pub mod bollinger;
pub mod adx;
pub mod aroon;
pub mod alma;
pub mod vwap;
pub mod fvg;
pub mod order_block;
pub mod candlestick_pattern;
pub mod per_candle_delta;
pub mod per_candle_absorption;
pub mod per_candle_zscore;
pub mod per_candle_imbalance;
pub mod atr;
pub mod pivot_points;
pub mod lvn;
pub mod mss;
pub mod cvd_divergence;
pub mod rvol;
pub mod sma;
pub mod ema;

/// UI adapter methods for converting domain `BasisSeries` into plot-ready series.
trait BasisSeriesExt<T> {
    fn as_plot_series(&self) -> AnySeries<'_, T>;
}

impl<T> BasisSeriesExt<T> for BasisSeries<T> {
    fn as_plot_series(&self) -> AnySeries<'_, T> {
        match self {
            BasisSeries::Time(data) => AnySeries::forward_unix_ms(data),
            BasisSeries::Tick(data) => AnySeries::reversed_u64(data),
        }
    }
}

#[allow(dead_code)]
#[derive(Debug, Clone, Default, PartialEq)]
pub enum IndicatorAvailability {
    /// Indicator can be rendered normally.
    #[default]
    Available,
    /// Availability cannot be determined yet (e.g. no datapoints loaded).
    Unknown,
    /// Indicator cannot be rendered for the current source/context.
    Unavailable(AvailabilityCause),
}

#[allow(dead_code)]
#[derive(Debug, Clone, PartialEq)]
pub enum AvailabilityCause {
    Exchange(Exchange),
    Timeframe(Timeframe),
    Basis(Basis),
    TradeData,
}

impl IndicatorAvailability {
    pub fn unavailable_message(&self, indicator: &str) -> Option<String> {
        match self {
            IndicatorAvailability::Available | IndicatorAvailability::Unknown => None,
            IndicatorAvailability::Unavailable(cause) => Some(match cause {
                AvailabilityCause::Exchange(exchange) => {
                    format!("{indicator} is not available for {exchange}.")
                }
                AvailabilityCause::Timeframe(timeframe) => {
                    format!("{indicator} is not available on {timeframe} timeframe.")
                }
                AvailabilityCause::Basis(Basis::Tick(_)) => {
                    format!("{indicator} is not available for tick charts.")
                }
                AvailabilityCause::Basis(basis) => {
                    format!("{indicator} is not available on {basis} basis.")
                }
                AvailabilityCause::TradeData => {
                    format!("{indicator} requires directional trade-volume data.")
                }
            }),
        }
    }
}

pub trait KlineIndicatorImpl {
    /// Clear all caches for a full redraw
    fn clear_all_caches(&mut self);

    /// Clear caches related to crosshair only
    fn clear_crosshair_caches(&mut self);

    fn element<'a>(
        &'a self,
        chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: std::ops::RangeInclusive<u64>,
    ) -> iced::Element<'a, Message>;

    fn availability(&self, _chart: &ViewState) -> IndicatorAvailability {
        IndicatorAvailability::Available
    }

    fn unavailable_message(&self, chart: &ViewState, indicator: &str) -> Option<String> {
        self.availability(chart).unavailable_message(indicator)
    }

    fn fetch_range(&mut self, _ctx: &FetchCtx) -> Option<FetchRange> {
        None
    }

    fn rebuild_from_source(&mut self, _source: &PlotData<KlineDataPoint>) {}

    fn on_insert_klines(&mut self, _klines: &[Kline], _source: &PlotData<KlineDataPoint>) {}

    fn on_insert_trades(
        &mut self,
        _trades: &[Trade],
        _old_dp_len: usize,
        _source: &PlotData<KlineDataPoint>,
    ) {
    }

    fn on_ticksize_change(&mut self, _source: &PlotData<KlineDataPoint>) {}

    fn on_basis_change(&mut self, _source: &PlotData<KlineDataPoint>) {}

    fn on_open_interest(&mut self, _pairs: &[exchange::OpenInterest]) {}

    fn apply_config(&mut self, config: &IndicatorConfig) {}

    /// Whether this indicator should be drawn on the candle chart itself
    /// (overlay) rather than in a separate sub-panel.
    fn is_overlay(&self) -> bool {
        false
    }

    /// Draw the indicator directly onto the candle chart's canvas frame.
    ///
    /// The frame uses the candle chart's coordinate system — use `ctx.price_to_y()`
    /// to convert price values to y-pixels and `ctx.interval_to_x()` for x-pixels.
    fn draw_overlay(
        &self,
        _frame: &mut Frame,
        _ctx: &ViewState,
        _theme: &Theme,
        _visible_range: RangeInclusive<u64>,
    ) {
    }
}

pub struct FetchCtx<'a> {
    pub main_chart: &'a ViewState,
    pub timeframe: Timeframe,
    pub visible_earliest: UnixMs,
    pub kline_latest: UnixMs,
    pub prefetch_earliest: UnixMs,
}

pub fn make_empty(which: KlineIndicator) -> Box<dyn KlineIndicatorImpl> {
    make_with_config(which, &HashMap::new())
}

pub fn make_with_config(
    which: KlineIndicator,
    params: &IndicatorConfigs,
) -> Box<dyn KlineIndicatorImpl> {
    let default = IndicatorConfig::for_kline(which);
    let config = params.get(&which).unwrap_or(&default);
    let mut indi: Box<dyn KlineIndicatorImpl> = match which {
        KlineIndicator::Volume => Box::new(super::kline::volume::VolumeIndicator::new()),
        KlineIndicator::CumulativeDelta => {
            Box::new(super::kline::cumulative_delta::CumulativeDeltaIndicator::new())
        }
        KlineIndicator::OpenInterest => {
            Box::new(super::kline::open_interest::OpenInterestIndicator::new())
        }
        KlineIndicator::Rsi => Box::new(super::kline::rsi::RsiIndicator::new()),
        KlineIndicator::Macd => Box::new(super::kline::macd::MacdIndicator::new()),
        KlineIndicator::BollingerBands => {
            Box::new(super::kline::bollinger::BollingerIndicator::new())
        }
        KlineIndicator::Adx => Box::new(super::kline::adx::AdxIndicator::new()),
        KlineIndicator::Aroon => Box::new(super::kline::aroon::AroonIndicator::new()),
        KlineIndicator::Alma => Box::new(super::kline::alma::AlmaIndicator::new()),
        KlineIndicator::Vwap => Box::new(super::kline::vwap::VwapIndicator::new()),
        KlineIndicator::Fvg => Box::new(super::kline::fvg::FvgIndicator::new()),
        KlineIndicator::OrderBlock => {
            Box::new(super::kline::order_block::OrderBlockIndicator::new())
        }
        KlineIndicator::Candlestick => {
            Box::new(
                super::kline::candlestick_pattern::CandlestickPatternIndicator::new(),
            )
        }
        KlineIndicator::PerCandleDelta => {
            Box::new(super::kline::per_candle_delta::PerCandleDeltaIndicator::new())
        }
        KlineIndicator::PerCandleAbsorption => {
            Box::new(super::kline::per_candle_absorption::PerCandleAbsorptionIndicator::new())
        }
        KlineIndicator::PerCandleZScore => {
            Box::new(super::kline::per_candle_zscore::PerCandleZScoreIndicator::new())
        }
        KlineIndicator::PerCandleImbalance => {
            Box::new(super::kline::per_candle_imbalance::PerCandleImbalanceIndicator::new())
        }
        KlineIndicator::Lvn => {
            Box::new(super::kline::lvn::LvnIndicator::new())
        }
        KlineIndicator::Atr => {
            Box::new(super::kline::atr::AtrIndicator::new())
        }
        KlineIndicator::PivotPoints => {
            Box::new(super::kline::pivot_points::PivotPointsIndicator::new())
        }
        KlineIndicator::Mss => {
            Box::new(super::kline::mss::MssIndicator::new())
        }
        KlineIndicator::CvdDivergence => {
            Box::new(super::kline::cvd_divergence::CvdDivergenceIndicator::new())
        }
        KlineIndicator::Rvol => {
            Box::new(super::kline::rvol::RvolIndicator::new())
        }
        KlineIndicator::Sma => {
            Box::new(super::kline::sma::SmaIndicator::new())
        }
        KlineIndicator::Ema => {
            Box::new(super::kline::ema::EmaIndicator::new())
        }
    };
    indi.apply_config(config);
    indi
}
