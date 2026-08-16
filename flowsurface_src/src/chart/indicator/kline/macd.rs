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

/// MACD indicator point with histogram for bar-style sub-rendering.
#[derive(Debug, Clone, Copy, Default)]
pub struct MacdPoint {
    pub macd_line: f32,
    pub signal: f32,
    pub histogram: f32,
}

pub struct MacdIndicator {
    cache: Caches,
    data: BasisSeries<MacdPoint>,
    fast_period: usize,
    slow_period: usize,
    signal_period: usize,
}

impl MacdIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            fast_period: 12,
            slow_period: 26,
            signal_period: 9,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &MacdPoint, _next: Option<&MacdPoint>| {
            PlotTooltip::new(format!(
                "MACD: {:.2}\nSignal: {:.2}\nHist: {:.2}",
                point.macd_line, point.signal, point.histogram
            ))
        };

        let value_fn = |point: &MacdPoint| point.histogram.abs();

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
                let closes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                if closes.len() < self.slow_period + 1 { return; }
                let macd_result = ta::macd(&closes, self.fast_period, self.slow_period, self.signal_period);
                let result: std::collections::BTreeMap<UnixMs, MacdPoint> = ts.datapoints.iter().zip(macd_result.iter())
                    .filter_map(|((&t, _), m)| {
                        m.map(|v| (t, MacdPoint {
                            macd_line: v.macd_line,
                            signal: v.signal,
                            histogram: v.histogram,
                        }))
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();
                if closes.len() < self.slow_period + 1 { return; }
                let macd_result = ta::macd(&closes, self.fast_period, self.slow_period, self.signal_period);
                let result: std::collections::BTreeMap<u64, MacdPoint> = tick.datapoints.iter().enumerate().zip(macd_result.iter())
                    .filter_map(|((i, _), m)| {
                        m.map(|v| (i as u64, MacdPoint {
                            macd_line: v.macd_line,
                            signal: v.signal,
                            histogram: v.histogram,
                        }))
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for MacdIndicator {
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
        if let IndicatorConfig::Macd { fast_period, slow_period, signal_period } = config {
            self.fast_period = *fast_period;
            self.slow_period = *slow_period;
            self.signal_period = *signal_period;
        }
    }
}