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

/// Aroon indicator point — up/down lines and oscillator.
#[derive(Debug, Clone, Copy, Default)]
pub struct AroonPoint {
    pub up: f32,
    pub down: f32,
    pub oscillator: f32,
}

pub struct AroonIndicator {
    cache: Caches,
    data: BasisSeries<AroonPoint>,
    period: usize,
}

impl AroonIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            period: 25,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &AroonPoint, _next: Option<&AroonPoint>| {
            PlotTooltip::new(format!(
                "Aroon Up: {:.1}\nAroon Down: {:.1}\nOsc: {:.1}",
                point.up, point.down, point.oscillator
            ))
        };

        let value_fn = |point: &AroonPoint| point.oscillator;

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
                if highs.len() < self.period + 1 { return; }
                let aroon_result = ta::aroon(&highs, &lows, self.period);
                let result: std::collections::BTreeMap<UnixMs, AroonPoint> = ts.datapoints.iter().zip(aroon_result.iter())
                    .filter_map(|((&t, _), aroon_opt)| {
                        aroon_opt.map(|v| (t, AroonPoint {
                            up: v.up,
                            down: v.down,
                            oscillator: v.oscillator,
                        }))
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let highs: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.low.to_f32()).collect();
                if highs.len() < self.period + 1 { return; }
                let aroon_result = ta::aroon(&highs, &lows, self.period);
                let result: std::collections::BTreeMap<u64, AroonPoint> = tick.datapoints.iter().enumerate().zip(aroon_result.iter())
                    .filter_map(|((i, _), aroon_opt)| {
                        aroon_opt.map(|v| (i as u64, AroonPoint {
                            up: v.up,
                            down: v.down,
                            oscillator: v.oscillator,
                        }))
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for AroonIndicator {
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
        if let IndicatorConfig::Aroon { period } = config {
            self.period = *period;
        }
    }
}