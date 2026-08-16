pub struct Config {
    pub pair: String,
    pub timeframe: String,
    pub market: String,
    pub max_candles: usize,
    pub redis_url: String,
    pub ws_ping_interval_secs: u64,
    pub reconnect_max_retries: u32,
    pub reconnect_base_delay_ms: u64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            pair: "BTC/USDT".to_string(),
            timeframe: "1h".to_string(),
            market: "futures".to_string(),
            max_candles: 600,
            redis_url: "redis://127.0.0.1:6379".to_string(),
            ws_ping_interval_secs: 30,
            reconnect_max_retries: 5,
            reconnect_base_delay_ms: 1000,
        }
    }
}

fn parse_args() -> Config {
    let mut c = Config::default();
    let args: Vec<String> = std::env::args().collect();
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--pair" | "-p" => { i += 1; if i < args.len() { c.pair = args[i].clone(); } }
            "--timeframe" | "-t" => { i += 1; if i < args.len() { c.timeframe = args[i].clone(); } }
            "--market" | "-m" => { i += 1; if i < args.len() { c.market = args[i].clone(); } }
            "--max-candles" | "-c" => { i += 1; if i < args.len() { c.max_candles = args[i].parse().unwrap_or(600); } }
            "--redis-url" | "-r" => { i += 1; if i < args.len() { c.redis_url = args[i].clone(); } }
            _ => {}
        }
        i += 1;
    }
    c
}

pub fn get_config() -> Config {
    parse_args()
}
