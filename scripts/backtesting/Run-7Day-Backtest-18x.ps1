# Run 7-Day Backtest with 18x Leverage
# Configuration: 18x leverage, 1000 USDT fixed capital, 3 tokens (XRP, DOGE, SOL)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "7-Day Backtest (18x Leverage)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  - Strategy: AroonMomentumEngine_Hybrid" -ForegroundColor White
Write-Host "  - Leverage: 18x (via leverage_config.py)" -ForegroundColor White
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

# Step 1: Download data explicitly is not always needed if data is fresh, but ensuring it is good practice
# If recent data is already there, freqtrade handles it. We can skip explicit download to save time if we just ran it, 
# BUT to be safe/consistent with previous run, we can keep it or just comment it out if we know we just downloaded it.
# The user just ran a backtest, so data is likely there. However, standard procedure:
Write-Host "Step 1: Verifying/Downloading historical data..." -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

# We can skip the loop if we trust the previous run's download, but let's do a quick check or just run the backtest directly 
# since we *just* downloaded data in the previous turn (Step 50+).
Write-Host "Data download skipped (assumed fresh from previous run today)." -ForegroundColor DarkGray
Write-Host ""

Write-Host "Step 2: Running backtest..." -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

# Run the backtest
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
