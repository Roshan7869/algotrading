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
use data::chart::{PlotData, kline::KlineDataPoint, ta};
use exchange::{Kline, Trade, Volume};

use std::ops::RangeInclusive;

#[derive(Debug, Clone, Copy, Default)]
pub struct ZScorePoint {
    pub zscore: f32,
}

pub struct PerCandleZScoreIndicator {
    cache: Caches,
    data: BasisSeries<ZScorePoint>,
    lookback: usize,
    stddev_threshold: f32,
    availability: IndicatorAvailability,
}

impl PerCandleZScoreIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            lookback: 20,
            stddev_threshold: 2.0,
            availability: IndicatorAvailability::Unknown,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        if let Some(message) = self.unavailable_message(main_chart, "Delta Z-Score") {
            return iced::widget::center(iced::widget::text(message)).into();
        }

        let tooltip = |point: &ZScorePoint, _next: Option<&ZScorePoint>| {
            PlotTooltip::new(format!("Z-Score: {:.2}", point.zscore))
        };

        let value_fn = |point: &ZScorePoint| point.zscore;

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

    fn delta_from_footprint(footprint: &data::chart::kline::KlineTrades, volume: Volume) -> f32 {
        if footprint.trades.is_empty() {
            volume.buy_sell()
                .map(|(b, s)| b.to_f32_lossy() - s.to_f32_lossy())
                .unwrap_or(0.0)
        } else {
            footprint.trades.values().map(|g| g.delta_qty().to_f32_lossy()).sum()
        }
    }

    fn has_directional(footprint: &data::chart::kline::KlineTrades, volume: Volume) -> bool {
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
                let deltas: Vec<f32> = ts.datapoints.values().map(|dp| {
                    Self::delta_from_footprint(&dp.footprint, dp.kline.volume)
                }).collect();
                let timestamps: Vec<u64> = ts.datapoints.iter().map(|(&t, _)| t.as_u64()).collect();

                if deltas.len() < self.lookback + 1 { return; }

                let zscores = ta::delta_zscore_series(&deltas, self.lookback);
                let result: std::collections::BTreeMap<_, ZScorePoint> = timestamps.iter().zip(zscores.iter())
                    .filter_map(|(&t, z)| z.map(|v| (t.into(), ZScorePoint { zscore: v })))
                    .collect();
                self.data = BasisSeries::Time(result);
                self.set_availability(has_points, has_directional);
            }
            PlotData::TickBased(tick) => {
                let has_points = !tick.datapoints.is_empty();
                let has_directional = tick.datapoints.iter().any(|dp| {
                    Self::has_directional(&dp.footprint, dp.kline.volume)
                });
                let deltas: Vec<f32> = tick.datapoints.iter().map(|dp| {
                    Self::delta_from_footprint(&dp.footprint, dp.kline.volume)
                }).collect();

                if deltas.len() < self.lookback + 1 { return; }

                let zscores = ta::delta_zscore_series(&deltas, self.lookback);
                let result: std::collections::BTreeMap<_, ZScorePoint> = zscores.iter().enumerate()
                    .filter_map(|(i, z)| z.map(|v| (i as u64, ZScorePoint { zscore: v })))
                    .collect();
                self.data = BasisSeries::Tick(result);
                self.set_availability(has_points, has_directional);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for PerCandleZScoreIndicator {
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
        if let IndicatorConfig::PerCandleZScore { lookback, stddev_threshold } = config {
            self.lookback = *lookback;
            self.stddev_threshold = *stddev_threshold;
        }
    }
}
