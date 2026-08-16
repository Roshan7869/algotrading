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

/// RSI indicator point — stores the computed RSI value.
#[derive(Debug, Clone, Copy, Default)]
pub struct RsiPoint {
    pub rsi: f32,
}

pub struct RsiIndicator {
    cache: Caches,
    data: BasisSeries<RsiPoint>,
    period: usize,
    overbought: f32,
    oversold: f32,
}

impl RsiIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            period: 14,
            overbought: 70.0,
            oversold: 30.0,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &RsiPoint, _next: Option<&RsiPoint>| {
            PlotTooltip::new(format!("RSI: {:.1}", point.rsi))
        };

        let value_fn = |point: &RsiPoint| point.rsi;

        let plot = LinePlot::new(value_fn)
            .stroke_width(1.5)
            .show_points(true)
            .point_radius_factor(0.2)
            .padding(0.05)
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
                let closes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                if closes.len() < self.period + 1 { return; }
                let rsi_vals = ta::rsi(&closes, self.period);
                let result: std::collections::BTreeMap<UnixMs, RsiPoint> = ts.datapoints.iter().zip(rsi_vals.iter())
                    .filter_map(|((&t, _), rsi_opt)| {
                        rsi_opt.map(|v| (t, RsiPoint { rsi: v }))
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();
                if closes.len() < self.period + 1 { return; }
                let rsi_vals = ta::rsi(&closes, self.period);
                let result: std::collections::BTreeMap<u64, RsiPoint> = tick.datapoints.iter().enumerate().zip(rsi_vals.iter())
                    .filter_map(|((i, _), rsi_opt)| {
                        rsi_opt.map(|v| (i as u64, RsiPoint { rsi: v }))
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for RsiIndicator {
    fn clear_all_caches(&mut self) {
        self.cache.clear_all();
    }

    fn clear_crosshair_caches(&mut self) {
        self.cache.clear_crosshair();
    }

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
        if let IndicatorConfig::Rsi { period, overbought, oversold } = config {
            self.period = *period;
            self.overbought = *overbought;
            self.oversold = *oversold;
        }
    }
}