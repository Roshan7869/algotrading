use std::collections::BTreeMap;

use data::chart::orderflow;
use iced::widget::canvas::Path;

use crate::chart::{Message, ViewState};

pub fn orderflow_cvd_view<'a>(
    _chart: &'a ViewState,
    cvd_line: &'a [(u64, f32)],
    config: orderflow::Config,
) -> iced::Element<'a, Message> {
    let cvd_color: iced::Color = config.color_cvd.to_iced();

    if cvd_line.is_empty() {
        return iced::widget::container(
            iced::widget::text("CVD: no data").size(12),
        )
        .padding(4)
        .into();
    }

    let cvd_data: BTreeMap<u64, f32> = cvd_line.iter().copied().collect();
    iced::widget::canvas::Canvas::new(CvdCanvas {
        data: cvd_data,
        color: cvd_color,
    })
    .width(iced::Length::Fill)
    .height(iced::Length::Fill)
    .into()
}

pub fn orderflow_delta_view(
    _chart: &ViewState,
    mut buckets: Vec<(u64, f32, f32)>,
    config: orderflow::Config,
) -> iced::Element<'static, Message> {
    let bid_color: iced::Color = config.color_bid.to_iced();
    let ask_color: iced::Color = config.color_ask.to_iced();

    buckets.sort_by_key(|(ts, _, _)| *ts);

    iced::widget::canvas::Canvas::new(DeltaCanvas {
        buckets,
        bid_color,
        ask_color,
    })
    .width(iced::Length::Fill)
    .height(iced::Length::Fill)
    .into()
}

pub fn orderflow_absorption_view<'a>(
    _chart: &'a ViewState,
    latest_klines: &'a BTreeMap<u64, exchange::Kline>,
    config: orderflow::Config,
) -> iced::Element<'a, Message> {
    let mut klines: Vec<&exchange::Kline> = latest_klines.values().collect();
    klines.sort_by_key(|k| k.time);

    if klines.len() < 20 {
        return iced::widget::container(
            iced::widget::text("Absorption: need 20+ candles")
                .size(12)
                .color(iced::Color::from_rgb(0.5, 0.5, 0.5)),
        )
        .padding(4)
        .into();
    }

    let avg_vol: f32 = klines
        .iter()
        .map(|k| k.volume.total().to_f32_lossy())
        .sum::<f32>()
        / klines.len() as f32;

    let avg_range: f32 = klines
        .iter()
        .map(|k| k.high.to_f32() - k.low.to_f32())
        .sum::<f32>()
        / klines.len() as f32;

    let mut signals: Vec<(u64, bool)> = Vec::new();
    for k in klines.iter().skip(20) {
        let vol = k.volume.total().to_f32_lossy();
        let range = k.high.to_f32() - k.low.to_f32();
        if vol > avg_vol * config.absorption_multiplier
            && range < avg_range * config.absorption_range_multiplier
        {
            let is_bullish = k.close.to_f32() > k.open.to_f32();
            signals.push((k.time.as_u64(), is_bullish));
        }
    }

    iced::widget::canvas::Canvas::new(AbsorptionCanvas { signals })
        .width(iced::Length::Fill)
        .height(iced::Length::Fill)
        .into()
}

struct CvdCanvas {
    data: BTreeMap<u64, f32>,
    color: iced::Color,
}

impl iced::widget::canvas::Program<Message> for CvdCanvas {
    type State = ();
    fn update(
        &self,
        _: &mut Self::State,
        _: &iced::widget::canvas::Event,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Option<iced::widget::canvas::Action<Message>> {
        None
    }
    fn draw(
        &self,
        _: &Self::State,
        renderer: &iced::Renderer,
        _: &iced::Theme,
        bounds: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Vec<iced::widget::canvas::Geometry> {
        let cache = iced::widget::canvas::Cache::default();
        let geo = cache.draw(renderer, bounds.size(), |frame| {
            if self.data.len() < 2 {
                return;
            }
            let entries: Vec<_> = self.data.iter().collect();
            let max_y = entries
                .iter()
                .map(|(_, v)| v.abs())
                .fold(0.0_f32, |a, b| a.max(b))
                .max(1.0);
            let n = entries.len() as f32;
            for i in 1..entries.len() {
                let x1 = bounds.x + bounds.width * (i - 1) as f32 / n;
                let x2 = bounds.x + bounds.width * i as f32 / n;
                let y1 =
                    bounds.y + bounds.height * 0.5
                        - (entries[i - 1].1 / max_y) * bounds.height * 0.5;
                let y2 = bounds.y + bounds.height * 0.5
                    - (entries[i].1 / max_y) * bounds.height * 0.5;
                frame.stroke(
                    &Path::line(
                        iced::Point::new(x1, y1),
                        iced::Point::new(x2, y2),
                    ),
                    iced::widget::canvas::Stroke {
                        style: iced::widget::canvas::Style::Solid(self.color),
                        width: 1.5,
                        ..Default::default()
                    },
                );
            }
            let zero_y = bounds.y + bounds.height * 0.5;
            frame.stroke(
                &Path::line(
                    iced::Point::new(bounds.x, zero_y),
                    iced::Point::new(bounds.x + bounds.width, zero_y),
                ),
                iced::widget::canvas::Stroke {
                    style: iced::widget::canvas::Style::Solid(iced::Color::from_rgb(0.3, 0.3, 0.3)),
                    width: 0.5,
                    ..Default::default()
                },
            );
        });
        vec![geo]
    }
    fn mouse_interaction(
        &self,
        _: &Self::State,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> iced::mouse::Interaction {
        iced::mouse::Interaction::default()
    }
}

struct DeltaCanvas {
    buckets: Vec<(u64, f32, f32)>,
    bid_color: iced::Color,
    ask_color: iced::Color,
}

impl iced::widget::canvas::Program<Message> for DeltaCanvas {
    type State = ();
    fn update(
        &self,
        _: &mut Self::State,
        _: &iced::widget::canvas::Event,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Option<iced::widget::canvas::Action<Message>> {
        None
    }
    fn draw(
        &self,
        _: &Self::State,
        renderer: &iced::Renderer,
        _: &iced::Theme,
        bounds: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Vec<iced::widget::canvas::Geometry> {
        let cache = iced::widget::canvas::Cache::default();
        let geo = cache.draw(renderer, bounds.size(), |frame| {
            if self.buckets.is_empty() {
                return;
            }
            let max_vol = self
                .buckets
                .iter()
                .map(|(_, b, s)| b + s)
                .fold(0.0_f32, |a, v| a.max(v))
                .max(1.0);
            let n = self.buckets.len() as f32;
            let bw = (bounds.width / n).max(1.0);
            let bh = bounds.height;
            for (i, &(_, buy, sell)) in self.buckets.iter().enumerate() {
                let x = bounds.x + i as f32 * bw;
                let buy_h = (buy / max_vol) * bh;
                let sell_h = (sell / max_vol) * bh;
                frame.fill_rectangle(
                    iced::Point::new(x, bounds.y),
                    iced::Size::new(bw - 1.0, buy_h),
                    self.bid_color,
                );
                frame.fill_rectangle(
                    iced::Point::new(x, bounds.y + buy_h),
                    iced::Size::new(bw - 1.0, sell_h),
                    self.ask_color,
                );
            }
        });
        vec![geo]
    }
    fn mouse_interaction(
        &self,
        _: &Self::State,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> iced::mouse::Interaction {
        iced::mouse::Interaction::default()
    }
}

pub fn orderflow_delta_zscore_view<'a>(
    _chart: &'a ViewState,
    trades_by_bucket: &BTreeMap<u64, (f32, f32)>,
    config: orderflow::Config,
) -> iced::Element<'a, Message> {
    let lookback = config.delta_zscore_lookback as usize;

    let mut buckets: Vec<(u64, f32, f32)> = trades_by_bucket
        .iter()
        .map(|(&ts, &(buy, sell))| (ts, buy, sell))
        .collect();
    buckets.sort_by_key(|(ts, _, _)| *ts);

    if buckets.len() < lookback {
        return iced::widget::container(
            iced::widget::text(format!("Delta Z-Score: need {}+ buckets", lookback))
                .size(12)
                .color(iced::Color::from_rgb(0.5, 0.5, 0.5)),
        )
        .padding(4)
        .into();
    }

    // Compute per-bucket delta and then rolling z-score
    let deltas: Vec<(u64, f32)> = buckets
        .iter()
        .map(|&(ts, buy, sell)| (ts, buy - sell))
        .collect();

    let mut z_scores: Vec<(u64, f32)> = Vec::new();
    for i in (lookback - 1)..deltas.len() {
        let window: Vec<f32> = deltas[i - lookback + 1..=i].iter().map(|(_, d)| *d).collect();
        let mean = window.iter().sum::<f32>() / window.len() as f32;
        let variance = window.iter().map(|d| (d - mean).powi(2)).sum::<f32>() / window.len() as f32;
        let stddev = variance.sqrt().max(1e-6);
        let z = (deltas[i].1 - mean) / stddev;
        z_scores.push((deltas[i].0, z));
    }

    iced::widget::canvas::Canvas::new(DeltaZScoreCanvas { z_scores })
        .width(iced::Length::Fill)
        .height(iced::Length::Fill)
        .into()
}

pub fn orderflow_imbalance_ratio_view<'a>(
    _chart: &'a ViewState,
    trades_by_bucket: &BTreeMap<u64, (f32, f32)>,
    config: orderflow::Config,
) -> iced::Element<'a, Message> {
    let window_size = config.imbalance_ratio_window as usize;

    let mut buckets: Vec<(u64, f32, f32)> = trades_by_bucket
        .iter()
        .map(|(&ts, &(buy, sell))| (ts, buy, sell))
        .collect();
    buckets.sort_by_key(|(ts, _, _)| *ts);

    if buckets.len() < window_size {
        return iced::widget::container(
            iced::widget::text(format!("Imbalance Ratio: need {}+ buckets", window_size))
                .size(12)
                .color(iced::Color::from_rgb(0.5, 0.5, 0.5)),
        )
        .padding(4)
        .into();
    }

    // Compute rolling imbalance ratio: buy / (buy + sell), normalized around 0.5
    let mut imbalance: Vec<(u64, f32)> = Vec::new();
    for i in (window_size - 1)..buckets.len() {
        let window = &buckets[i - window_size + 1..=i];
        let total_buy: f32 = window.iter().map(|(_, b, _)| *b).sum();
        let total_sell: f32 = window.iter().map(|(_, _, s)| *s).sum();
        let total = total_buy + total_sell;
        let ratio = if total > 0.0 {
            total_buy / total
        } else {
            0.5
        };
        // Normalize: 0 = full sell imbalance, 1 = full buy imbalance, 0.5 = balanced
        imbalance.push((buckets[i].0, ratio));
    }

    iced::widget::canvas::Canvas::new(ImbalanceRatioCanvas { imbalance })
        .width(iced::Length::Fill)
        .height(iced::Length::Fill)
        .into()
}

struct DeltaZScoreCanvas {
    z_scores: Vec<(u64, f32)>,
}

impl iced::widget::canvas::Program<Message> for DeltaZScoreCanvas {
    type State = ();
    fn update(
        &self,
        _: &mut Self::State,
        _: &iced::widget::canvas::Event,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Option<iced::widget::canvas::Action<Message>> {
        None
    }
    fn draw(
        &self,
        _: &Self::State,
        renderer: &iced::Renderer,
        _: &iced::Theme,
        bounds: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Vec<iced::widget::canvas::Geometry> {
        let cache = iced::widget::canvas::Cache::default();
        let geo = cache.draw(renderer, bounds.size(), |frame| {
            if self.z_scores.len() < 2 {
                return;
            }
            let max_z = self
                .z_scores
                .iter()
                .map(|(_, z)| z.abs())
                .fold(0.0_f32, |a, b| a.max(b))
                .max(1.0);
            let n = self.z_scores.len() as f32;
            for i in 1..self.z_scores.len() {
                let x1 = bounds.x + bounds.width * (i - 1) as f32 / n;
                let x2 = bounds.x + bounds.width * i as f32 / n;
                let y1 = bounds.y + bounds.height * 0.5
                    - (self.z_scores[i - 1].1 / max_z) * bounds.height * 0.5;
                let y2 = bounds.y + bounds.height * 0.5
                    - (self.z_scores[i].1 / max_z) * bounds.height * 0.5;
                let color = if self.z_scores[i].1 >= 0.0 {
                    iced::Color::from_rgb(0.0, 0.8, 0.4)
                } else {
                    iced::Color::from_rgb(0.8, 0.2, 0.2)
                };
                frame.stroke(
                    &Path::line(iced::Point::new(x1, y1), iced::Point::new(x2, y2)),
                    iced::widget::canvas::Stroke {
                        style: iced::widget::canvas::Style::Solid(color),
                        width: 1.5,
                        ..Default::default()
                    },
                );
            }
            let zero_y = bounds.y + bounds.height * 0.5;
            frame.stroke(
                &Path::line(
                    iced::Point::new(bounds.x, zero_y),
                    iced::Point::new(bounds.x + bounds.width, zero_y),
                ),
                iced::widget::canvas::Stroke {
                    style: iced::widget::canvas::Style::Solid(iced::Color::from_rgb(0.3, 0.3, 0.3)),
                    width: 0.5,
                    ..Default::default()
                },
            );
            for &threshold in &[-2.0_f32, 2.0_f32] {
                let ty = bounds.y + bounds.height * 0.5
                    - (threshold / max_z) * bounds.height * 0.5;
                frame.stroke(
                    &Path::line(
                        iced::Point::new(bounds.x, ty),
                        iced::Point::new(bounds.x + bounds.width, ty),
                    ),
                    iced::widget::canvas::Stroke {
                        style: iced::widget::canvas::Style::Solid(iced::Color::from_rgb(
                            0.4, 0.4, 0.2,
                        )),
                        width: 0.5,
                        ..Default::default()
                    },
                );
            }
        });
        vec![geo]
    }
    fn mouse_interaction(
        &self,
        _: &Self::State,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> iced::mouse::Interaction {
        iced::mouse::Interaction::default()
    }
}

struct ImbalanceRatioCanvas {
    imbalance: Vec<(u64, f32)>,
}

impl iced::widget::canvas::Program<Message> for ImbalanceRatioCanvas {
    type State = ();
    fn update(
        &self,
        _: &mut Self::State,
        _: &iced::widget::canvas::Event,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Option<iced::widget::canvas::Action<Message>> {
        None
    }
    fn draw(
        &self,
        _: &Self::State,
        renderer: &iced::Renderer,
        _: &iced::Theme,
        bounds: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Vec<iced::widget::canvas::Geometry> {
        let cache = iced::widget::canvas::Cache::default();
        let geo = cache.draw(renderer, bounds.size(), |frame| {
            if self.imbalance.len() < 2 {
                return;
            }
            let n = self.imbalance.len() as f32;
            for i in 1..self.imbalance.len() {
                let x1 = bounds.x + bounds.width * (i - 1) as f32 / n;
                let x2 = bounds.x + bounds.width * i as f32 / n;
                let y1 = bounds.y + bounds.height * (1.0 - self.imbalance[i - 1].1);
                let y2 = bounds.y + bounds.height * (1.0 - self.imbalance[i].1);
                let color = if self.imbalance[i].1 > 0.55 {
                    iced::Color::from_rgb(0.0, 0.8, 0.4)
                } else if self.imbalance[i].1 < 0.45 {
                    iced::Color::from_rgb(0.8, 0.2, 0.2)
                } else {
                    iced::Color::from_rgb(0.5, 0.5, 0.5)
                };
                frame.stroke(
                    &Path::line(iced::Point::new(x1, y1), iced::Point::new(x2, y2)),
                    iced::widget::canvas::Stroke {
                        style: iced::widget::canvas::Style::Solid(color),
                        width: 1.5,
                        ..Default::default()
                    },
                );
            }
            let mid_y = bounds.y + bounds.height * 0.5;
            frame.stroke(
                &Path::line(
                    iced::Point::new(bounds.x, mid_y),
                    iced::Point::new(bounds.x + bounds.width, mid_y),
                ),
                iced::widget::canvas::Stroke {
                    style: iced::widget::canvas::Style::Solid(iced::Color::from_rgb(0.3, 0.3, 0.3)),
                    width: 0.5,
                    ..Default::default()
                },
            );
        });
        vec![geo]
    }
    fn mouse_interaction(
        &self,
        _: &Self::State,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> iced::mouse::Interaction {
        iced::mouse::Interaction::default()
    }
}

struct AbsorptionCanvas {
    signals: Vec<(u64, bool)>,
}

impl iced::widget::canvas::Program<Message> for AbsorptionCanvas {
    type State = ();
    fn update(
        &self,
        _: &mut Self::State,
        _: &iced::widget::canvas::Event,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Option<iced::widget::canvas::Action<Message>> {
        None
    }
    fn draw(
        &self,
        _: &Self::State,
        renderer: &iced::Renderer,
        _: &iced::Theme,
        bounds: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> Vec<iced::widget::canvas::Geometry> {
        let cache = iced::widget::canvas::Cache::default();
        let geo = cache.draw(renderer, bounds.size(), |frame| {
            if self.signals.is_empty() {
                return;
            }
            let ts_min = self.signals.first().map(|(t, _)| *t).unwrap_or(0);
            let ts_max = self.signals.last().map(|(t, _)| *t).unwrap_or(1);
            let ts_range = (ts_max - ts_min).max(1) as f32;
            for &(ts, is_bullish) in &self.signals {
                let x = bounds.x + bounds.width * (ts - ts_min) as f32 / ts_range;
                let color = if is_bullish {
                    iced::Color::from_rgb(0.0, 1.0, 0.0)
                } else {
                    iced::Color::from_rgb(1.0, 0.0, 0.0)
                };
                let s = 4.0;
                frame.fill_rectangle(
                    iced::Point::new(x - s / 2.0, bounds.y + bounds.height * 0.5 - s / 2.0),
                    iced::Size::new(s, s),
                    color,
                );
            }
        });
        vec![geo]
    }
    fn mouse_interaction(
        &self,
        _: &Self::State,
        _: iced::Rectangle,
        _: iced::mouse::Cursor,
    ) -> iced::mouse::Interaction {
        iced::mouse::Interaction::default()
    }
}
