use crate::chart::{
    Caches, Message, ViewState,
    indicator::{
        indicator_row,
        kline::{
            AvailabilityCause, BasisSeries, BasisSeriesExt, IndicatorAvailability,
            KlineIndicatorImpl,
        },
        plot::{PlotTooltip, bar::{BarClass, BarPlot}},
    },
};

use data::chart::indicator::IndicatorConfig;
use data::chart::{
    PlotData,
    kline::{KlineDataPoint, KlineTrades},
};
use exchange::{Kline, Trade, Volume};

use std::ops::RangeInclusive;

#[derive(Debug, Clone, Copy, Default)]
pub struct PerCandleDeltaPoint {
    pub delta: f32,
}

pub struct PerCandleDeltaIndicator {
    cache: Caches,
    data: BasisSeries<PerCandleDeltaPoint>,
    availability: IndicatorAvailability,
}

impl PerCandleDeltaIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            availability: IndicatorAvailability::Unknown,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        if let Some(message) = self.unavailable_message(main_chart, "Delta") {
            return iced::widget::center(iced::widget::text(message)).into();
        }

        let tooltip = |point: &PerCandleDeltaPoint, _next: Option<&PerCandleDeltaPoint>| {
            let sign = if point.delta >= 0.0 { "+" } else { "" };
            PlotTooltip::new(format!("Delta: {}{:.2}", sign, point.delta))
        };

        let value_fn = |point: &PerCandleDeltaPoint| point.delta;

        let bar_kind = |_: &PerCandleDeltaPoint| BarClass::Single;

        let plot = BarPlot::new(value_fn, bar_kind)
            .bar_width_factor(0.6)
            .padding(0.08)
            .with_tooltip(tooltip);

        indicator_row(
            main_chart,
            &self.cache,
            data_labels_always_visible,
            plot,
            self.data.as_plot_series(),
            visible_range,
        )
    }

    fn delta_from_footprint(footprint: &KlineTrades, volume: Volume) -> f32 {
        if footprint.trades.is_empty() {
            volume.buy_sell()
                .map(|(b, s)| b.to_f32_lossy() - s.to_f32_lossy())
                .unwrap_or(0.0)
        } else {
            footprint.trades.values().map(|g| g.delta_qty().to_f32_lossy()).sum()
        }
    }

    fn has_directional(footprint: &KlineTrades, volume: Volume) -> bool {
        !footprint.trades.is_empty() || volume.buy_sell().is_some()
    }

    fn set_availability(&mut self, has_points: bool, has_directional: bool) {
        self.availability = if !has_points {
            IndicatorAvailability::Unknown
        } else if has_directional {
            IndicatorAvailability::Available
        } else {
            IndicatorAvailability::Unavailable(AvailabilityCause::TradeData)
        };
    }

    fn rebuild_from_source(&mut self, source: &PlotData<KlineDataPoint>) {
        match source {
            PlotData::TimeBased(ts) => {
                let has_points = !ts.datapoints.is_empty();
                let has_directional = ts.datapoints.values().any(|dp| {
                    Self::has_directional(&dp.footprint, dp.kline.volume)
                });
                let deltas: std::collections::BTreeMap<_, _> = ts.datapoints.iter()
                    .map(|(&t, dp)| (t, PerCandleDeltaPoint {
                        delta: Self::delta_from_footprint(&dp.footprint, dp.kline.volume),
                    }))
                    .collect();
                self.data = BasisSeries::Time(deltas);
                self.set_availability(has_points, has_directional);
            }
            PlotData::TickBased(tick) => {
                let has_points = !tick.datapoints.is_empty();
                let has_directional = tick.datapoints.iter().any(|dp| {
                    Self::has_directional(&dp.footprint, dp.kline.volume)
                });
                let deltas: std::collections::BTreeMap<_, _> = tick.datapoints.iter().enumerate()
                    .map(|(i, dp)| (i as u64, PerCandleDeltaPoint {
                        delta: Self::delta_from_footprint(&dp.footprint, dp.kline.volume),
                    }))
                    .collect();
                self.data = BasisSeries::Tick(deltas);
                self.set_availability(has_points, has_directional);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for PerCandleDeltaIndicator {
    fn clear_all_caches(&mut self) { self.cache.clear_all(); }
    fn clear_crosshair_caches(&mut self) { self.cache.clear_crosshair(); }

    fn element<'a>(
        &'a self,
        chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        self.indicator_elem(chart, data_labels_always_visible, visible_range)
    }

    fn availability(&self, _chart: &ViewState) -> IndicatorAvailability {
        self.availability.clone()
    }

    fn rebuild_from_source(&mut self, source: &PlotData<KlineDataPoint>) {
        self.rebuild_from_source(source);
    }

    fn on_insert_klines(&mut self, _klines: &[Kline], source: &PlotData<KlineDataPoint>) {
        self.rebuild_from_source(source);
    }

    fn on_insert_trades(
        &mut self,
        _trades: &[Trade],
        _old_dp_len: usize,
        source: &PlotData<KlineDataPoint>,
    ) {
        self.rebuild_from_source(source);
        self.availability = IndicatorAvailability::Available;
    }

    fn on_basis_change(&mut self, source: &PlotData<KlineDataPoint>) {
        self.rebuild_from_source(source);
    }

    fn apply_config(&mut self, _config: &IndicatorConfig) {}
}
