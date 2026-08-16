use crate::chart::{
    Caches, Message, ViewState,
    indicator::{
        indicator_row,
        kline::{BasisSeries, BasisSeriesExt, KlineIndicatorImpl},
        plot::{PlotTooltip, line::LinePlot},
    },
};

use data::chart::indicator::IndicatorConfig;
use data::chart::{PlotData, kline::KlineDataPoint, ta};
use exchange::{Kline, unit::UnixMs};

use std::ops::RangeInclusive;

#[derive(Debug, Clone, Copy, Default)]
pub struct AtrPoint {
    pub atr: f32,
}

pub struct AtrIndicator {
    cache: Caches,
    data: BasisSeries<AtrPoint>,
    period: usize,
}

impl AtrIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            period: 14,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &AtrPoint, _next: Option<&AtrPoint>| {
            PlotTooltip::new(format!("ATR: {:.4}", point.atr))
        };

        let value_fn = |point: &AtrPoint| point.atr;

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

    fn compute_from_source(&mut self, source: &PlotData<KlineDataPoint>) {
        match source {
            PlotData::TimeBased(ts) => {
                let highs: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.low.to_f32()).collect();
                let closes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                if closes.len() < self.period + 1 { return; }
                let atr_vals = ta::atr_series(&highs, &lows, &closes, self.period);
                let result: std::collections::BTreeMap<UnixMs, AtrPoint> = ts.datapoints.iter().zip(atr_vals.iter())
                    .filter_map(|((&t, _), a)| a.map(|v| (t, AtrPoint { atr: v })))
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let highs: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.low.to_f32()).collect();
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();
                if closes.len() < self.period + 1 { return; }
                let atr_vals = ta::atr_series(&highs, &lows, &closes, self.period);
                let result: std::collections::BTreeMap<u64, AtrPoint> = tick.datapoints.iter().enumerate().zip(atr_vals.iter())
                    .filter_map(|((i, _), a)| a.map(|v| (i as u64, AtrPoint { atr: v })))
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for AtrIndicator {
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

    fn rebuild_from_source(&mut self, source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn on_insert_klines(&mut self, _klines: &[Kline], source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn on_basis_change(&mut self, source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn apply_config(&mut self, config: &IndicatorConfig) {
        if let IndicatorConfig::Atr { period } = config {
            self.period = *period;
        }
    }
}
