# Run 24-Hour Backtest with Live Config (10x)
# Configuration: Uses user_data/config_live_trading_10x.json

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "24-Hour Backtest (Live Config 10x)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  - Strategy: AroonMomentumEngine_Hybrid" -ForegroundColor White
Write-Host "  - Config: user_data/config_live_trading_10x.json" -ForegroundColor White
Write-Host "  - Period: Last 24 Hours" -ForegroundColor White
Write-Host "  - Timeframes: 1h (Main), 4h (Informative)" -ForegroundColor White
Write-Host ""

# Calculate date range (2 days back to ensure full signal coverage for 24h test)
$endDate = Get-Date
$startDate = $endDate.AddDays(-2)
# Freqtrade format YYYYMMDD
$timerange = "{0}-{1}" -f $startDate.ToString("yyyyMMdd"), $endDate.ToString("yyyyMMdd")

Write-Host "Date Range: $timerange (Downloading 2 days for pre-roll)" -ForegroundColor Green
Write-Host ""

# Step 1: Download data
Write-Host "Step 1: Downloading historical data (1h & 4h)..." -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

# Download data for pairs in config + BTC for informative
# We use --days 2 to get enough data
docker run --rm `
    -v "${PWD}/user_data:/freqtrade/user_data" `
    freqtradeorg/freqtrade:stable `
    download-data `
    --config /freqtrade/user_data/config_live_trading_10x.json `
    --pairs BTC/USDT:USDT `
    --timeframes 1h 4h `
    --timerange $timerange

if ($LASTEXITCODE -ne 0) {
    Write-Host "Data download failed!" -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "Step 2: Running backtest..." -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

# Run the backtest
# We use a narrower timerange for the actual backtest if desired, or just run for the downloaded range.
# Let's run for the last 24 hours specifically for the report.
$backtestStartDate = $endDate.AddDays(-1)
$backtestTimerange = "{0}-{1}" -f $backtestStartDate.ToString("yyyyMMdd"), $endDate.ToString("yyyyMMdd")
Write-Host "Executing Backtest for: $backtestTimerange" -ForegroundColor Yellow

docker run --rm `
    -v "${PWD}/user_data:/freqtrade/user_data" `
    freqtradeorg/freqtrade:stable `
    backtesting `
    --config /freqtrade/user_data/config_live_trading_10x.json `
    --strategy AroonMomentumEngine_Hybrid `
    --timerange $backtestTimerange `
    --export trades `
    --breakdown day `
    --cache none

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "[OK] Backtest completed successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    
    # Step 3: Generate per-pair breakdown
    Write-Host "Step 3: Generating per-pair breakdown..." -ForegroundColor Cyan
    Write-Host "----------------------------------------" -ForegroundColor Gray
    
    docker run --rm `
        -v "${PWD}/user_data:/freqtrade/user_data" `
        freqtradeorg/freqtrade:stable `
        backtesting `
        --config /freqtrade/user_data/config_live_trading_10x.json `
        --strategy AroonMomentumEngine_Hybrid `
        --timerange $backtestTimerange `
        --breakdown pair `
        --cache none
        
}
else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "[ERROR] Backtest failed!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
}

Write-Host ""
Write-Host "Script completed." -ForegroundColor Cyan
