mod config;
mod candles;
mod ws;
mod indicators;
mod redis_pub;
mod execution;

use config::get_config;

#[tokio::main]
async fn main() {
    env_logger::init();
    let cfg = get_config();
    log::info!("ws-bridge starting: {} {} {}", cfg.pair, cfg.timeframe, cfg.market);
    log::info!("Redis: {}", cfg.redis_url);

    let ws_client = ws::BinanceWS::new(
        cfg.pair.clone(),
        cfg.timeframe.clone(),
        cfg.market.clone(),
        cfg.max_candles,
    );

    let candles = ws_client.candle_store();
    let publisher = redis_pub::RedisPublisher::new(
        cfg.redis_url.clone(),
        cfg.pair.clone(),
        cfg.timeframe.clone(),
        candles,
    );

    tokio::spawn(async move {
        run_publish_loop(publisher, &cfg.pair).await;
    });

    tokio::select! {
        _ = ws_client.run_with_reconnect() => {
            log::info!("WebSocket client finished");
        }
        _ = tokio::signal::ctrl_c() => {
            log::info!("Received Ctrl+C, shutting down");
        }
    }
}

async fn run_publish_loop(publisher: redis_pub::RedisPublisher, pair: &str) {
    let mut last_published: u64 = 0;
    let mut signal_engine = execution::SignalEngine::new(pair);
    let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(1));
    loop {
        interval.tick().await;
        let store = publisher.candles.lock().await;
        let latest_open = match store.latest() {
            Some(c) => c.open_time,
            None => continue,
        };
        if latest_open == last_published {
            continue;
        }
        last_published = latest_open;
        let candle = store.latest().unwrap().clone();
        let values = crate::indicators::IndicatorsEngine::compute(&store);
        drop(store);

        if let Err(e) = publisher.publish_candle(&candle).await {
            log::error!("Failed to publish candle: {}", e);
        }

        if let Err(e) = publisher.publish_indicators_from_values(&values, &candle).await {
            log::error!("Failed to publish indicators: {}", e);
        }

        let signals = signal_engine.evaluate(&values, candle.close);
        for signal in &signals {
            if let Err(e) = publisher.publish_signal(signal).await {
                log::error!("Failed to publish signal: {}", e);
            }
        }
    }
}
