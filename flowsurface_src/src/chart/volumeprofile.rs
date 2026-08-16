use std::collections::BTreeMap;
use std::time::Instant;

use data::chart::{Basis, ViewConfig, indicator::OrderFlowIndicator, volumeprofile::{self, CompositeMode}};
use exchange::{Kline, TickerInfo, Trade, UnixMs};
use exchange::unit::PriceStep;

use crate::chart::{
    Chart, Interaction, Message, PlotConstants, ViewState,
    Action, canvas_interaction,
};
use iced::widget::canvas::{self, Event, Geometry, Path, Stroke};
use crate::connector::fetcher::RequestHandler;

#[derive(Debug, Clone, Default)]
struct VolumeBin {
    total_vol: f32,
    buy_vol: f32,
    sell_vol: f32,
    tpo_count: u32,
    price_touched: bool,
}

pub struct VolumeProfileChart {
    chart: ViewState,
    pub visual_config: volumeprofile::Config,
    last_tick: Instant,
    request_handler: RequestHandler,
    volume_bins: BTreeMap<i64, VolumeBin>,
    latest_klines: BTreeMap<u64, Kline>,
    poc_price: Option<i64>,
    vah_price: Option<i64>,
    val_price: Option<i64>,
    naked_pocs: Vec<i64>,
}

impl VolumeProfileChart {
    pub fn new(
        layout: ViewConfig,
        basis: Basis,
        price_step: PriceStep,
        ticker_info: TickerInfo,
        visual_config: Option<volumeprofile::Config>,
    ) -> Self {
        let config = visual_config.unwrap_or_default();
        let decimals = (price_step.decimal_places() as f64).log10().ceil() as usize;
        let view_state = ViewState::new(basis, price_step, decimals, ticker_info, layout, 100.0, 4.0);

        VolumeProfileChart {
            chart: view_state,
            visual_config: config,
            last_tick: Instant::now(),
            request_handler: RequestHandler::default(),
            volume_bins: BTreeMap::new(),
            latest_klines: BTreeMap::new(),
            poc_price: None,
            vah_price: None,
            val_price: None,
            naked_pocs: Vec::new(),
        }
    }

    pub fn insert_trades(&mut self, buffer: &[Trade], _update_time: UnixMs) {
        for trade in buffer {
            let price_units = trade.price.units;
            let qty = trade.qty.to_f32_lossy();
            let bin = self.volume_bins.entry(price_units).or_default();
            match self.visual_config.composite_mode {
                CompositeMode::TotalVolume => bin.total_vol += qty,
                CompositeMode::DeltaVolume => {
                    if trade.is_sell { bin.sell_vol += qty; } else { bin.buy_vol += qty; }
                }
                CompositeMode::TpoCount => {
                    if !bin.price_touched { bin.tpo_count += 1; bin.price_touched = true; }
                }
            }
        }
        self.last_tick = Instant::now();
        self.recalculate_levels();
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
            let price_units = k.close.units;
            let bin = self.volume_bins.entry(price_units).or_default();
            let vol = k.volume.total().to_f32_lossy();
            bin.total_vol += vol;
            bin.tpo_count += 1;
            self.latest_klines.insert(k.time.as_u64(), k);
        }
        self.recalculate_levels();
    }

    fn recalculate_levels(&mut self) {
        if self.volume_bins.is_empty() { return; }

        let get_vol = |bin: &VolumeBin| -> f32 {
            match self.visual_config.composite_mode {
                CompositeMode::TotalVolume => bin.total_vol,
                CompositeMode::DeltaVolume => bin.buy_vol - bin.sell_vol,
                CompositeMode::TpoCount => bin.tpo_count as f32,
            }
        };

        let total_vol: f32 = self.volume_bins.values().map(get_vol).sum();
        if total_vol == 0.0 { return; }

        let mut poc_vol = 0.0f32;
        for (&price, bin) in &self.volume_bins {
            let v = get_vol(bin);
            if v > poc_vol { poc_vol = v; self.poc_price = Some(price); }
        }

        let target = total_vol * (self.visual_config.value_area_pct / 100.0);
        let mut sorted: Vec<_> = self.volume_bins.iter().map(|(p, b)| (*p, get_vol(b))).collect();
        sorted.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        let mut running: f32 = 0.0;
        let mut va_prices = Vec::new();
        for (price, vol) in &sorted {
            running += vol;
            va_prices.push(*price);
            if running >= target { break; }
        }
        self.vah_price = va_prices.iter().copied().max();
        self.val_price = va_prices.iter().copied().min();
    }

    pub fn chart_layout(&self) -> ViewConfig { self.chart.layout.clone() }
    pub fn last_update(&self) -> Instant { self.last_tick }

    fn invalidate_main_caches(&mut self) {
        self.chart.cache.main.clear();
        self.chart.cache.crosshair.clear();
    }
}

impl Chart for VolumeProfileChart {
    type IndicatorKind = OrderFlowIndicator;
    fn state(&self) -> &ViewState { &self.chart }
    fn mut_state(&mut self) -> &mut ViewState { &mut self.chart }
    fn invalidate_crosshair(&mut self) { self.chart.cache.crosshair.clear(); }
    fn invalidate_all(&mut self) { self.invalidate_main_caches(); }
    fn view_indicators(&self, _: &[Self::IndicatorKind]) -> Vec<iced::Element<'_, Message>> { vec![] }
    fn visible_timerange(&self) -> Option<(u64, u64)> { None }
    fn interval_keys(&self) -> Option<Vec<u64>> { None }
    fn autoscaled_coords(&self) -> iced::Vector { iced::Vector::new(0.0, 0.0) }
    fn supports_fit_autoscaling(&self) -> bool { true }
    fn is_empty(&self) -> bool { self.volume_bins.is_empty() }
}

impl PlotConstants for VolumeProfileChart {
    fn min_scaling(&self) -> f32 { 0.5 }
    fn max_scaling(&self) -> f32 { 10.0 }
    fn max_cell_width(&self) -> f32 { 200.0 }
    fn min_cell_width(&self) -> f32 { 20.0 }
    fn max_cell_height(&self) -> f32 { 10.0 }
    fn min_cell_height(&self) -> f32 { 1.0 }
    fn default_cell_width(&self) -> f32 { 100.0 }
}

impl iced::widget::canvas::Program<Message> for VolumeProfileChart {
    type State = Interaction;

    fn update(
        &self,
        interaction: &mut Self::State,
        event: &Event,
        bounds: iced::Rectangle,
        cursor: iced::mouse::Cursor,
    ) -> Option<canvas::Action<Message>> {
        super::canvas_interaction(self, interaction, event, bounds, cursor)
    }

    fn draw(
        &self, _interaction: &Self::State, renderer: &iced::Renderer, _theme: &iced::Theme,
        bounds: iced::Rectangle, _cursor: iced::mouse::Cursor,
    ) -> Vec<iced::widget::canvas::Geometry> {
        use iced::widget::canvas::{Path, Stroke, Style};
        let mut geometries = Vec::new();
        let cfg = &self.visual_config;

        let main_geo = self.chart.cache.main.draw(renderer, bounds.size(), |frame| {
            if self.volume_bins.is_empty() { return; }
            let max_vol: f32 = self.volume_bins.values().map(|b| b.total_vol).fold(0.0f32, |a: f32, b: f32| a.max(b));
            if max_vol == 0.0 { return; }

            let n_levels = self.volume_bins.len();
            let bar_h = (bounds.height / n_levels as f32).max(2.0);
            let prof_c = cfg.profile_color.to_iced();

            for (row, (_price, bin)) in self.volume_bins.iter().enumerate() {
                let bar_width = (bin.total_vol / max_vol) * bounds.width * 0.8;
                let y = bounds.y + row as f32 * bar_h;
                frame.fill_rectangle(
                    iced::Point::new(bounds.x + 10.0, y),
                    iced::Size::new(bar_width, bar_h - 1.0),
                    iced::Color::from_rgba(prof_c.r, prof_c.g, prof_c.b, 0.7),
                );
            }

            if let Some(vah) = self.vah_price {
                if let Some(idx) = self.volume_bins.keys().position(|&p| p == vah) {
                    let y = bounds.y + idx as f32 * bar_h;
                    frame.stroke(
                        &Path::line(iced::Point::new(bounds.x, y), iced::Point::new(bounds.x + bounds.width * 0.8, y)),
                        Stroke { style: Style::Solid(iced::Color::from_rgb(0.96, 0.26, 0.21)), width: 1.0, ..Default::default() },
                    );
                }
            }
            if let Some(val) = self.val_price {
                if let Some(idx) = self.volume_bins.keys().position(|&p| p == val) {
                    let y = bounds.y + idx as f32 * bar_h;
                    frame.stroke(
                        &Path::line(iced::Point::new(bounds.x, y), iced::Point::new(bounds.x + bounds.width * 0.8, y)),
                        Stroke { style: Style::Solid(iced::Color::from_rgb(0.30, 0.69, 0.31)), width: 1.0, ..Default::default() },
                    );
                }
            }
            if let Some(poc) = self.poc_price {
                if let Some(idx) = self.volume_bins.keys().position(|&p| p == poc) {
                    let y = bounds.y + idx as f32 * bar_h;
                    let poc_c = iced::Color::from_rgb(1.0, 0.92, 0.23);
                    frame.fill_rectangle(iced::Point::new(bounds.x, y), iced::Size::new(bounds.width * 0.8, bar_h),
                        iced::Color::from_rgba(poc_c.r, poc_c.g, poc_c.b, 0.3));
                    frame.fill_text(iced::widget::canvas::Text {
                        content: "POC".to_string(),
                        position: iced::Point::new(bounds.x + bounds.width * 0.82, y + bar_h * 0.7),
                        color: poc_c, size: iced::Pixels(10.0), ..Default::default()
                    });
                }
            }
        });

        geometries.push(main_geo);
        let crosshair_geo = self.chart.cache.crosshair.draw(renderer, bounds.size(), |_frame| {});
        geometries.push(crosshair_geo);
        geometries
    }

    fn mouse_interaction(
        &self, _interaction: &Self::State, _bounds: iced::Rectangle, _cursor: iced::mouse::Cursor,
    ) -> iced::mouse::Interaction {
        iced::mouse::Interaction::default()
    }
}
