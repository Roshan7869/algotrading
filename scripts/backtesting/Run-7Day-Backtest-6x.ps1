# Run 7-Day Backtest with 6x Leverage
# Configuration: 6x leverage, 1000 USDT fixed capital, 3 tokens (XRP, DOGE, SOL)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "7-Day Backtest (6x Leverage)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  - Strategy: AroonMomentumEngine_Hybrid" -ForegroundColor White
Write-Host "  - Leverage: 6x (via leverage_config.py)" -ForegroundColor White
Write-Host "  - Capital: 1000 USDT" -ForegroundColor White
Write-Host "  - Tokens: XRP, DOGE, SOL" -ForegroundColor White
Write-Host "  - Period: Last 7 Days" -ForegroundColor White
Write-Host "  - Timeframe: 1h" -ForegroundColor White
Write-Host ""

# Calculate date range (7 days back from today)
$endDate = Get-Date
$startDate = $endDate.AddDays(-7)
$timerange = "{0}-{1}" -f $startDate.ToString("yyyyMMdd"), $endDate.ToString("yyyyMMdd")

Write-Host "Date Range: $timerange" -ForegroundColor Green
Write-Host ""

# Pairs
$pairs = @("XRP/USDT:USDT", "DOGE/USDT:USDT", "SOL/USDT:USDT")

# Step 1: Download data
Write-Host "Step 1: Downloading historical data..." -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

foreach ($pair in $pairs) {
    Write-Host "Downloading data for $pair..." -ForegroundColor Yellow
    
    # Using generic config for download, strategy config usually not strictly needed for download but good practice
    # Using existing config_aroon_300day_backtest.json as base config
    docker run --rm `
        -v "${PWD}/user_data:/freqtrade/user_data" `
        freqtradeorg/freqtrade:stable `
        download-data `
        --config /freqtrade/user_data/config_aroon_300day_backtest.json `
        --pairs $pair `
        --timeframes 1h `
        --timerange $timerange `
        --exchange binance `
        --trading-mode futures
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Successfully downloaded $pair" -ForegroundColor Green
    }
    else {
        Write-Host "  [ERROR] Failed to download $pair" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host ""
Write-Host "Step 2: Running backtest..." -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

# Run the backtest
# Note: Using AroonMomentumEngine_Hybrid as identified in analysis
docker run --rm `
    -v "${PWD}/user_data:/freqtrade/user_data" `
    freqtradeorg/freqtrade:stable `
    backtesting `
    --config /freqtrade/user_data/config_aroon_300day_backtest.json `
    --strategy AroonMomentumEngine_Hybrid `
    --timeframe 1h `
    --timerange $timerange `
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
        --config /freqtrade/user_data/config_aroon_300day_backtest.json `
        --strategy AroonMomentumEngine_Hybrid `
        --timeframe 1h `
        --timerange $timerange `
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
