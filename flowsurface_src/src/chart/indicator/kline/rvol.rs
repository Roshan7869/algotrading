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
pub struct RvolPoint {
    pub rvol: f32,
}

pub struct RvolIndicator {
    cache: Caches,
    data: BasisSeries<RvolPoint>,
    lookback: usize,
    high_threshold: f32,
    low_threshold: f32,
}

impl RvolIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            lookback: 20,
            high_threshold: 2.0,
            low_threshold: 0.5,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let ht = self.high_threshold;
        let lt = self.low_threshold;

        let tooltip = move |point: &RvolPoint, _next: Option<&RvolPoint>| {
            let tag = if point.rvol > ht {
                "HIGH RVOL"
            } else if point.rvol < lt {
                "LOW RVOL"
            } else {
                "Normal"
            };
            PlotTooltip::new(format!("RVOL: {:.2}x\n{tag}", point.rvol))
        };

        let value_fn = |point: &RvolPoint| point.rvol;

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
                let volumes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.volume.total().to_f32_lossy()).collect();
                let timestamps: Vec<UnixMs> = ts.datapoints.iter().map(|(&t, _)| t).collect();

                if volumes.len() < self.lookback { return; }

                let rvol_vals = ta::rvol_series(&volumes, self.lookback);

                let result: std::collections::BTreeMap<UnixMs, RvolPoint> = timestamps.iter().enumerate()
                    .filter_map(|(i, &t)| rvol_vals[i].map(|v| (t, RvolPoint { rvol: v })))
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let volumes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.volume.total().to_f32_lossy()).collect();

                if volumes.len() < self.lookback { return; }

                let rvol_vals = ta::rvol_series(&volumes, self.lookback);

                let result: std::collections::BTreeMap<u64, RvolPoint> = rvol_vals.iter().enumerate()
                    .filter_map(|(i, v)| v.map(|r| (i as u64, RvolPoint { rvol: r })))
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for RvolIndicator {
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
        if let IndicatorConfig::Rvol { lookback, high_threshold, low_threshold } = config {
            self.lookback = *lookback;
            self.high_threshold = *high_threshold;
            self.low_threshold = *low_threshold;
        }
    }
}
