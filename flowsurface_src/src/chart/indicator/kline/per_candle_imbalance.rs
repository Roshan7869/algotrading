use crate::chart::{
    Caches, Message, ViewState,
    indicator::{
        indicator_row,
        kline::{
            AvailabilityCause, BasisSeries, BasisSeriesExt, IndicatorAvailability,
            KlineIndicatorImpl,
        },
        plot::{PlotTooltip, line::LinePlot},
    },
};

use data::chart::indicator::IndicatorConfig;
use data::chart::{
    PlotData,
    kline::{KlineDataPoint, KlineTrades},
    ta,
};
use exchange::{Kline, Trade, Volume};

use std::ops::RangeInclusive;

#[derive(Debug, Clone, Copy, Default)]
pub struct ImbalancePoint {
    pub ratio: f32,
}

pub struct PerCandleImbalanceIndicator {
    cache: Caches,
    data: BasisSeries<ImbalancePoint>,
    lookback: usize,
    threshold: f32,
    availability: IndicatorAvailability,
}

impl PerCandleImbalanceIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            lookback: 14,
            threshold: 0.6,
            availability: IndicatorAvailability::Unknown,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        if let Some(message) = self.unavailable_message(main_chart, "Imbalance") {
            return iced::widget::center(iced::widget::text(message)).into();
        }

        let tooltip = |point: &ImbalancePoint, _next: Option<&ImbalancePoint>| {
            PlotTooltip::new(format!("Imbalance: {:.2}", point.ratio))
        };

        let value_fn = |point: &ImbalancePoint| point.ratio;

        let plot = LinePlot::new(value_fn)
            .stroke_width(1.5)
            .show_points(true)
            .point_radius_factor(0.2)
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

    fn buy_sell_from_footprint(footprint: &KlineTrades, volume: Volume) -> (f32, f32) {
        if footprint.trades.is_empty() {
            volume.buy_sell()
                .map(|(b, s)| (b.to_f32_lossy(), s.to_f32_lossy()))
                .unwrap_or((0.0, 0.0))
        } else {
            let mut buy = 0.0_f32;
            let mut sell = 0.0_f32;
            for group in footprint.trades.values() {
                buy += group.buy_qty.to_f32_lossy();
                sell += group.sell_qty.to_f32_lossy();
            }
            (buy, sell)
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

    fn compute_from_source(&mut self, source: &PlotData<KlineDataPoint>) {
        match source {
            PlotData::TimeBased(ts) => {
                let has_points = !ts.datapoints.is_empty();
                let has_directional = ts.datapoints.values().any(|dp| {
                    Self::has_directional(&dp.footprint, dp.kline.volume)
                });
                let buys: Vec<f32> = ts.datapoints.values().map(|dp| {
                    Self::buy_sell_from_footprint(&dp.footprint, dp.kline.volume).0
                }).collect();
                let sells: Vec<f32> = ts.datapoints.values().map(|dp| {
                    Self::buy_sell_from_footprint(&dp.footprint, dp.kline.volume).1
                }).collect();
                let timestamps: Vec<u64> = ts.datapoints.iter().map(|(&t, _)| t.as_u64()).collect();

                if buys.len() < self.lookback + 1 { return; }

                let ratios = ta::imbalance_ratio_series(&buys, &sells, self.lookback);
                let result: std::collections::BTreeMap<_, ImbalancePoint> = timestamps.iter().zip(ratios.iter())
                    .filter_map(|(&t, r)| r.map(|v| (t.into(), ImbalancePoint { ratio: v })))
                    .collect();
                self.data = BasisSeries::Time(result);
                self.set_availability(has_points, has_directional);
            }
            PlotData::TickBased(tick) => {
                let has_points = !tick.datapoints.is_empty();
                let has_directional = tick.datapoints.iter().any(|dp| {
                    Self::has_directional(&dp.footprint, dp.kline.volume)
                });
                let buys: Vec<f32> = tick.datapoints.iter().map(|dp| {
                    Self::buy_sell_from_footprint(&dp.footprint, dp.kline.volume).0
                }).collect();
                let sells: Vec<f32> = tick.datapoints.iter().map(|dp| {
                    Self::buy_sell_from_footprint(&dp.footprint, dp.kline.volume).1
                }).collect();

                if buys.len() < self.lookback + 1 { return; }

                let ratios = ta::imbalance_ratio_series(&buys, &sells, self.lookback);
                let result: std::collections::BTreeMap<_, ImbalancePoint> = ratios.iter().enumerate()
                    .filter_map(|(i, r)| r.map(|v| (i as u64, ImbalancePoint { ratio: v })))
                    .collect();
                self.data = BasisSeries::Tick(result);
                self.set_availability(has_points, has_directional);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for PerCandleImbalanceIndicator {
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
        self.compute_from_source(source);
    }

    fn on_insert_klines(&mut self, _klines: &[Kline], source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn on_insert_trades(
        &mut self,
        _trades: &[Trade],
        _old_dp_len: usize,
        source: &PlotData<KlineDataPoint>,
    ) {
        self.compute_from_source(source);
        self.availability = IndicatorAvailability::Available;
    }

    fn on_basis_change(&mut self, source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn apply_config(&mut self, config: &IndicatorConfig) {
        if let IndicatorConfig::PerCandleImbalance { lookback, threshold } = config {
            self.lookback = *lookback;
            self.threshold = *threshold;
        }
    }
}
