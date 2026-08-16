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
use exchange::{Kline, unit::{Price, UnixMs}};

use iced::widget::canvas::{Frame, Path, Stroke};
use iced::{Color, Point, Theme};

use std::ops::RangeInclusive;

#[derive(Debug, Clone, Copy, Default)]
pub struct SmaPoint {
    pub sma: f32,
}

pub struct SmaIndicator {
    cache: Caches,
    data: BasisSeries<SmaPoint>,
    period: usize,
    color: Color,
}

impl SmaIndicator {
    pub fn new() -> Self {
        Self {
            cache: Caches::default(),
            data: BasisSeries::default(),
            period: 20,
            color: Color::from_rgb(1.0, 0.84, 0.0),
        }
    }

    fn compute_from_source(&mut self, source: &PlotData<KlineDataPoint>) {
        match source {
            PlotData::TimeBased(ts) => {
                let closes: Vec<f32> = ts.datapoints.iter().map(|(_, dp)| dp.kline.close.to_f32()).collect();
                if closes.len() < self.period { return; }
                let sma_vals = ta::sma_series(&closes, self.period);
                let result: std::collections::BTreeMap<UnixMs, SmaPoint> = ts.datapoints.iter().zip(sma_vals.iter())
                    .filter_map(|((&t, _), opt)| opt.map(|v| (t, SmaPoint { sma: v })))
                    .collect();
                self.data = BasisSeries::Time(result);
            }
            PlotData::TickBased(tick) => {
                let closes: Vec<f32> = tick.datapoints.iter().map(|dp| dp.kline.close.to_f32()).collect();
                if closes.len() < self.period { return; }
                let sma_vals = ta::sma_series(&closes, self.period);
                let result: std::collections::BTreeMap<u64, SmaPoint> = sma_vals.iter().enumerate()
                    .filter_map(|(i, opt)| opt.map(|v| (i as u64, SmaPoint { sma: v })))
                    .collect();
                self.data = BasisSeries::Tick(result);
            }
        }
        self.clear_all_caches();
    }
}

impl KlineIndicatorImpl for SmaIndicator {
    fn clear_all_caches(&mut self) { self.cache.clear_all(); }
    fn clear_crosshair_caches(&mut self) { self.cache.clear_crosshair(); }

    fn is_overlay(&self) -> bool { true }

    fn draw_overlay(&self, frame: &mut Frame, ctx: &ViewState, _theme: &Theme, visible_range: RangeInclusive<u64>) {
        let earliest = *visible_range.start();
        let latest = *visible_range.end();

        let points: Vec<(u64, &SmaPoint)> = match &self.data {
            BasisSeries::Time(map) => {
                let er = UnixMs(earliest); let lr = UnixMs(latest);
                map.range(er..=lr).map(|(&k, v)| (k.0, v)).collect()
            }
            BasisSeries::Tick(map) => {
                map.range(earliest..=latest).map(|(&k, v)| (k, v)).collect()
            }
        };

        if points.len() < 2 { return; }

        let path = Path::new(|builder| {
            let mut first = true;
            for &(ts, pt) in &points {
                let x = ctx.interval_to_x(ts);
                let y = ctx.price_to_y(Price::from_f32_lossy(pt.sma));
                if first { builder.move_to(Point::new(x, y)); first = false; }
                else { builder.line_to(Point::new(x, y)); }
            }
        });

        frame.stroke(&path, Stroke::default().with_width(1.2).with_color(self.color));
    }

    fn element<'a>(&'a self, chart: &'a ViewState, _data_labels_always_visible: bool, _visible_range: RangeInclusive<u64>) -> iced::Element<'a, Message> {
        // SMA is overlay-only, but need to implement to satisfy trait
        iced::widget::column![].into()
    }

    fn rebuild_from_source(&mut self, source: &PlotData<KlineDataPoint>) { self.compute_from_source(source); }
    fn on_insert_klines(&mut self, _klines: &[Kline], source: &PlotData<KlineDataPoint>) { self.compute_from_source(source); }
    fn on_basis_change(&mut self, source: &PlotData<KlineDataPoint>) { self.compute_from_source(source); }

    fn apply_config(&mut self, config: &IndicatorConfig) {
        if let IndicatorConfig::Sma { period, color } = config {
            self.period = *period;
            if let Ok(c) = parse_hex_color(color) { self.color = c; }
        }
    }
}

pub fn parse_hex_color(hex: &str) -> Result<Color, ()> {
    let h = hex.trim_start_matches('#');
    if h.len() == 6 {
        let r = u8::from_str_radix(&h[0..2], 16).map_err(|_| ())?;
        let g = u8::from_str_radix(&h[2..4], 16).map_err(|_| ())?;
        let b = u8::from_str_radix(&h[4..6], 16).map_err(|_| ())?;
        Ok(Color::from_rgb(r as f32 / 255.0, g as f32 / 255.0, b as f32 / 255.0))
    } else {
        Err(())
    }
}
