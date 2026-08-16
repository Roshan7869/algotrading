use std::collections::BTreeMap;
use std::time::Instant;

use data::chart::{Basis, ViewConfig, indicator::OrderFlowIndicator, orderflow};
use exchange::{Kline, TickerInfo, Trade, UnixMs};
use exchange::unit::{PriceStep, Qty};

use crate::chart::{
    Chart, Caches, Interaction, Message, PlotConstants, ViewState,
    Action, canvas_interaction,
};
use crate::connector::fetcher::RequestHandler;

#[derive(Debug, Clone, Default)]
pub struct DeltaBucket {
    pub buy_volume: f32,
    pub sell_volume: f32,
}

impl DeltaBucket {
    fn delta(&self) -> f32 { self.buy_volume - self.sell_volume }
    fn total(&self) -> f32 { self.buy_volume + self.sell_volume }
}

pub struct OrderflowChart {
    chart: ViewState,
    pub visual_config: orderflow::Config,
    last_tick: Instant,
    request_handler: RequestHandler,
    pub trades_by_bucket: BTreeMap<u64, BTreeMap<i64, DeltaBucket>>,
    pub cvd_line: Vec<(u64, f32)>,
    pub latest_klines: BTreeMap<u64, Kline>,
    delta_map: BTreeMap<u64, (f32, f32)>,
}

impl OrderflowChart {
    pub fn new(
        layout: ViewConfig,
        basis: Basis,
        price_step: PriceStep,
        ticker_info: TickerInfo,
        visual_config: Option<orderflow::Config>,
    ) -> Self {
        let config = visual_config.unwrap_or_default();
        let decimals = (price_step.decimal_places() as f64).log10().ceil() as usize;
        let view_state = ViewState::new(
            basis,
            price_step,
            decimals,
            ticker_info,
            layout,
            10.0,
            4.0,
        );

        OrderflowChart {
            chart: view_state,
            visual_config: config,
            last_tick: Instant::now(),
            request_handler: RequestHandler::default(),
            trades_by_bucket: BTreeMap::new(),
            cvd_line: Vec::new(),
            latest_klines: BTreeMap::new(),
            delta_map: BTreeMap::new(),
        }
    }

    pub fn insert_trades(&mut self, buffer: &[Trade], _update_time: UnixMs) {
        for trade in buffer {
            let bucket_ms = {
                let raw = trade.time.as_u64();
                let window = (self.visual_config.delta_aggr_seconds as u64) * 1000;
                (raw / window) * window
            };
            let price_units = trade.price.units;
            let bucket = self.trades_by_bucket
                .entry(bucket_ms).or_default()
                .entry(price_units).or_default();
            let qty = trade.qty.to_f32_lossy();
            if trade.is_sell { bucket.sell_volume += qty; }
            else { bucket.buy_volume += qty; }
        }
        self.last_tick = Instant::now();
        self.recalculate_cvd();
    }

    pub fn insert_raw_trades(&mut self, trades: Vec<Trade>) {
        let now = UnixMs::new(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH).unwrap()
                .as_millis() as u64,
        );
        self.insert_trades(&trades, now);
    }

    pub fn update_latest_kline(&mut self, kline: &Kline) {
        self.latest_klines.insert(kline.time.as_u64(), *kline);
    }

    pub fn insert_hist_klines(&mut self, klines: Vec<Kline>) {
        for k in klines {
            self.latest_klines.insert(k.time.as_u64(), k);
        }
    }

    fn recalculate_cvd(&mut self) {
        self.cvd_line.clear();
        let mut running: f32 = 0.0;
        for (&bucket_ms, price_map) in self.trades_by_bucket.iter() {
            let delta: f32 = price_map.values().map(|b| b.delta()).sum();
            running += delta;
            self.cvd_line.push((bucket_ms, running));
        }
    }

    pub fn chart_layout(&self) -> ViewConfig { self.chart.layout.clone() }
    pub fn last_update(&self) -> Instant { self.last_tick }

    fn invalidate_main_caches(&mut self) {
        self.chart.cache.main.clear();
        self.chart.cache.crosshair.clear();
    }
}

impl Chart for OrderflowChart {
    type IndicatorKind = OrderFlowIndicator;
    fn state(&self) -> &ViewState { &self.chart }
    fn mut_state(&mut self) -> &mut ViewState { &mut self.chart }
    fn invalidate_crosshair(&mut self) { self.chart.cache.crosshair.clear(); }
    fn invalidate_all(&mut self) { self.invalidate_main_caches(); }

    fn view_indicators(&self, enabled: &[Self::IndicatorKind]) -> Vec<iced::Element<'_, Message>> {
        use crate::chart::indicator::orderflow as of;
        let mut rows = Vec::new();
        for ind in enabled {
            match ind {
                OrderFlowIndicator::Cvd => {
                    rows.push(of::orderflow_cvd_view(&self.chart, &self.cvd_line, self.visual_config));
                }
                OrderFlowIndicator::Delta => {
                    let delta_map: BTreeMap<u64, (f32, f32)> = self.trades_by_bucket
                        .iter()
                        .map(|(&ts, pm)| {
                            let buy: f32 = pm.values().map(|b| b.buy_volume).sum();
                            let sell: f32 = pm.values().map(|b| b.sell_volume).sum();
                            (ts, (buy, sell))
                        })
                        .collect();
                    let delta_vec: Vec<(u64, f32, f32)> = delta_map.into_iter().map(|(ts, (b, s))| (ts, b, s)).collect();
                    rows.push(of::orderflow_delta_view(&self.chart, delta_vec, self.visual_config));
                }
                OrderFlowIndicator::Absorption => {
                    rows.push(of::orderflow_absorption_view(&self.chart, &self.latest_klines, self.visual_config));
                }
                OrderFlowIndicator::DeltaZscore => {
                    let delta_owned: BTreeMap<u64, (f32, f32)> = self.trades_by_bucket
                        .iter()
                        .map(|(&ts, pm)| {
                            let buy: f32 = pm.values().map(|b| b.buy_volume).sum();
                            let sell: f32 = pm.values().map(|b| b.sell_volume).sum();
                            (ts.into(), (buy, sell))
                        })
                        .collect();
                    rows.push(of::orderflow_delta_zscore_view(&self.chart, &delta_owned, self.visual_config));
                }
                OrderFlowIndicator::ImbalanceRatio => {
                    let delta_owned: BTreeMap<u64, (f32, f32)> = self.trades_by_bucket
                        .iter()
                        .map(|(&ts, pm)| {
                            let buy: f32 = pm.values().map(|b| b.buy_volume).sum();
                            let sell: f32 = pm.values().map(|b| b.sell_volume).sum();
                            (ts.into(), (buy, sell))
                        })
                        .collect();
                    rows.push(of::orderflow_imbalance_ratio_view(&self.chart, &delta_owned, self.visual_config));
                }
            }
        }
        rows
    }

    fn visible_timerange(&self) -> Option<(u64, u64)> {
        let first = self.trades_by_bucket.keys().next().copied();
        let last = self.trades_by_bucket.keys().next_back().copied();
        match (first, last) {
            (Some(f), Some(l)) => Some((f, l)),
            _ => None,
        }
    }

    fn interval_keys(&self) -> Option<Vec<u64>> {
        Some(self.trades_by_bucket.keys().copied().collect())
    }

    fn autoscaled_coords(&self) -> iced::Vector { iced::Vector::new(0.0, 0.0) }
    fn supports_fit_autoscaling(&self) -> bool { true }
    fn is_empty(&self) -> bool { self.trades_by_bucket.is_empty() }
}

impl PlotConstants for OrderflowChart {
    fn min_scaling(&self) -> f32 { 0.5 }
    fn max_scaling(&self) -> f32 { 10.0 }
    fn max_cell_width(&self) -> f32 { 30.0 }
    fn min_cell_width(&self) -> f32 { 3.0 }
    fn max_cell_height(&self) -> f32 { 20.0 }
    fn min_cell_height(&self) -> f32 { 2.0 }
    fn default_cell_width(&self) -> f32 { 10.0 }
}

impl iced::widget::canvas::Program<Message> for OrderflowChart {
    type State = Interaction;

    fn update(
        &self,
        interaction: &mut Interaction,
        event: &iced::widget::canvas::Event,
        bounds: iced::Rectangle,
        cursor: iced::mouse::Cursor,
    ) -> Option<iced::widget::canvas::Action<Message>> {
        super::canvas_interaction(self, interaction, event, bounds, cursor)
    }

    fn draw(
        &self,
        _interaction: &Interaction,
        renderer: &iced::Renderer,
        _theme: &iced::Theme,
        bounds: iced::Rectangle,
        _cursor: iced::mouse::Cursor,
    ) -> Vec<iced::widget::canvas::Geometry> {
        let mut geometries = Vec::new();
        let cfg = &self.visual_config;

        let main_geo = self.chart.cache.main.draw(renderer, bounds.size(), |frame| {
            use iced::widget::canvas::{Path, Stroke, Style};

            if self.trades_by_bucket.is_empty() { return; }

            let max_delta: f32 = self.trades_by_bucket
                .values().flat_map(|pm| pm.values().map(|b| b.delta().abs()))
                .fold(0.0, |a: f32, b: f32| a.max(b));

            if max_delta == 0.0 { return; }

            let n_buckets = self.trades_by_bucket.len() as f32;
            let cell_w = (bounds.width / n_buckets.max(1.0)).max(2.0);

            let max_price_buckets = self.trades_by_bucket
                .values().map(|pm| pm.len()).max().unwrap_or(1) as f32;
            let cell_h = (bounds.height / max_price_buckets.max(1.0)).max(2.0);

            for (col, (_ts, price_map)) in self.trades_by_bucket.iter().enumerate() {
                let x = bounds.x + col as f32 * cell_w;
                for (row, (_price_units, bucket)) in price_map.iter().enumerate() {
                    let y = bounds.y + row as f32 * cell_h;
                    let d = bucket.delta();
                    if d > 0.0 {
                        let intensity = (d / max_delta).min(1.0);
                        let c = cfg.color_bid.to_iced();
                        frame.fill_rectangle(
                            iced::Point::new(x, y),
                            iced::Size::new(cell_w - 1.0, cell_h - 1.0),
                            iced::Color::from_rgba(c.r, c.g, c.b, intensity * 0.9 + 0.1),
                        );
                    } else if d < 0.0 {
                        let intensity = (-d / max_delta).min(1.0);
                        let c = cfg.color_ask.to_iced();
                        frame.fill_rectangle(
                            iced::Point::new(x, y),
                            iced::Size::new(cell_w - 1.0, cell_h - 1.0),
                            iced::Color::from_rgba(c.r, c.g, c.b, intensity * 0.9 + 0.1),
                        );
                    }
                    if cfg.show_footprint_numbers && cell_w > 20.0 && cell_h > 8.0 {
                        frame.fill_text(iced::widget::canvas::Text {
                            content: format!("{:.0}", bucket.total()),
                            position: iced::Point::new(x + 1.0, y + 8.0),
                            color: iced::Color::WHITE,
                            size: iced::Pixels(8.0),
                            ..Default::default()
                        });
                    }
                }
            }

            let cvd_c = cfg.color_cvd.to_iced();
            for i in 1..self.cvd_line.len() {
                let x1 = bounds.x + (i - 1) as f32 * cell_w;
                let x2 = bounds.x + i as f32 * cell_w;
                let max_cvd: f32 = self.cvd_line.iter()
                    .map(|(_, v)| v.abs()).fold(0.0f32, |a: f32, b: f32| a.max(b)).max(1.0);
                let y1 = bounds.y + bounds.height * 0.95 - (self.cvd_line[i-1].1 / max_cvd) * bounds.height * 0.1;
                let y2 = bounds.y + bounds.height * 0.95 - (self.cvd_line[i].1 / max_cvd) * bounds.height * 0.1;
                frame.stroke(
                    &Path::line(iced::Point::new(x1, y1), iced::Point::new(x2, y2)),
                    Stroke { style: Style::Solid(cvd_c), width: 1.5, ..Default::default() },
                );
            }
        });

        let crosshair_geo = self.chart.cache.crosshair.draw(renderer, bounds.size(), |_frame| {});

        geometries.push(main_geo);
        geometries.push(crosshair_geo);
        geometries
    }

    fn mouse_interaction(
        &self, _interaction: &Self::State, _bounds: iced::Rectangle, _cursor: iced::mouse::Cursor,
    ) -> iced::mouse::Interaction {
        iced::mouse::Interaction::Crosshair
    }
}
