use crate::chart::{
    Caches, Message, ViewState,
    indicator::{
        indicator_row,
        kline::{BasisSeries, BasisSeriesExt, KlineIndicatorImpl},
        plot::{PlotTooltip, bar::{BarClass, BarPlot}},
    },
};

use data::chart::indicator::IndicatorConfig;
use data::chart::{PlotData, kline::KlineDataPoint, ta};
use exchange::{Kline, Trade, unit::UnixMs};

use std::ops::RangeInclusive;

#[derive(Debug, Clone, Copy, Default)]
pub struct AbsorptionPoint {
    pub value: f32,
    pub is_bullish: bool,
}

pub struct PerCandleAbsorptionIndicator {
    cache: Caches,
    data: BasisSeries<AbsorptionPoint>,
    vol_multiplier: f32,
    range_multiplier: f32,
    warmup: usize,
}

impl PerCandleAbsorptionIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            vol_multiplier: 1.5,
            range_multiplier: 0.5,
            warmup: 20,
        }
    }

    fn indicator_elem<'a>(
        &'a self,
        main_chart: &'a ViewState,
        data_labels_always_visible: bool,
        visible_range: RangeInclusive<u64>,
    ) -> iced::Element<'a, Message> {
        let tooltip = |point: &AbsorptionPoint, _next: Option<&AbsorptionPoint>| {
            let dir = if point.is_bullish { "Bull" } else { "Bear" };
            PlotTooltip::new(format!("Absorption ({dir})\nMag: {:.2}", point.value))
        };

        let value_fn = |point: &AbsorptionPoint| {
            if point.is_bullish { point.value } else { -point.value }
        };

        let bar_kind = |point: &AbsorptionPoint| {
            let v = if point.is_bullish { point.value } else { -point.value };
            BarClass::Overlay { overlay: v }
        };

        let plot = BarPlot::new(value_fn, bar_kind)
            .bar_width_factor(0.7)
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
                let opens: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.open.to_f32()).collect();
                let volumes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.volume.total().to_f32_lossy()).collect();
                let timestamps: Vec<UnixMs> = ts.datapoints.iter().map(|(&t, _)| t).collect();

                if highs.len() < self.warmup + 1 { return; }

                let bars = ta::detect_absorption(
                    &highs, &lows, &closes, &opens, &volumes,
                    self.vol_multiplier, self.range_multiplier, self.warmup,
                );

                let result: std::collections::BTreeMap<UnixMs, AbsorptionPoint> = bars.iter()
                    .filter_map(|b| {
                        timestamps.get(b.index).map(|&t| {
                            let body = (closes[b.index] - opens[b.index]).abs();
                            (t, AbsorptionPoint { value: body, is_bullish: b.is_bullish })
                        })
                    })
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let highs: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.high.to_f32()).collect();
                let lows: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.low.to_f32()).collect();
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();
                let opens: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.open.to_f32()).collect();
                let volumes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.volume.total().to_f32_lossy()).collect();

                if highs.len() < self.warmup + 1 { return; }

                let bars = ta::detect_absorption(
                    &highs, &lows, &closes, &opens, &volumes,
                    self.vol_multiplier, self.range_multiplier, self.warmup,
                );

                let result: std::collections::BTreeMap<u64, AbsorptionPoint> = bars.iter()
                    .map(|b| {
                        let idx = b.index as u64;
                        let body = (closes[b.index] - opens[b.index]).abs();
                        (idx, AbsorptionPoint { value: body, is_bullish: b.is_bullish })
                    })
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for PerCandleAbsorptionIndicator {
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

    fn on_insert_trades(
        &mut self,
        _trades: &[Trade],
        _old_dp_len: usize,
        source: &PlotData<KlineDataPoint>,
    ) {
        self.compute_from_source(source);
    }

    fn on_basis_change(&mut self, source: &PlotData<KlineDataPoint>) {
        self.compute_from_source(source);
    }

    fn apply_config(&mut self, config: &IndicatorConfig) {
        if let IndicatorConfig::PerCandleAbsorption { vol_multiplier, range_multiplier, warmup } = config {
            self.vol_multiplier = *vol_multiplier;
            self.range_multiplier = *range_multiplier;
            self.warmup = *warmup;
        }
    }
}
