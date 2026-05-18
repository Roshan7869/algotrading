# Run 48-Hour Backtest with Live Config (10x)
# Configuration: Uses user_data/config_live_trading_10x.json

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "48-Hour Backtest (Live Config 10x)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  - Strategy: AroonMomentumEngine_Hybrid" -ForegroundColor White
Write-Host "  - Config: user_data/config_live_trading_10x.json" -ForegroundColor White
Write-Host "  - Period: Last 48 Hours" -ForegroundColor White
Write-Host "  - Timeframes: 1h (Main), 4h (Informative)" -ForegroundColor White
Write-Host ""

# Calculate date range (4 days back to ensure full signal coverage for 48h test and indicators)
$endDate = Get-Date
$startDate = $endDate.AddDays(-4)
# Freqtrade format YYYYMMDD
$timerange = "{0}-{1}" -f $startDate.ToString("yyyyMMdd"), $endDate.ToString("yyyyMMdd")

Write-Host "Date Range for Download: $timerange" -ForegroundColor Green
Write-Host ""

# Step 1: Download data
Write-Host "Step 1: Downloading historical data (1h & 4h)..." -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

# Download data for pairs in config + BTC for informative
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

# Run the backtest for the last 48 hours
$backtestStartDate = $endDate.AddDays(-2)
$backtestTimerange = "{0}-{1}" -f $backtestStartDate.ToString("yyyyMMdd"), $endDate.ToString("yyyyMMdd")
Write-Host "Executing Backtest for: $backtestTimerange" -ForegroundColor Yellow

# We capture output to file directly here to avoid re-running
docker run --rm `
    -v "${PWD}/user_data:/freqtrade/user_data" `
    freqtradeorg/freqtrade:stable `
    backtesting `
    --config /freqtrade/user_data/config_live_trading_10x.json `
    --strategy AroonMomentumEngine_Hybrid `
    --timerange $backtestTimerange `
    --export trades `
    --breakdown day `
    --cache none | Tee-Object -FilePath "user_data/backtest_results_48h.txt"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "[OK] Backtest completed successfully!" -ForegroundColor Green
    Write-Host "Results saved to user_data/backtest_results_48h.txt" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
}
else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "[ERROR] Backtest failed!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
}

Write-Host ""
Write-Host "Script completed." -ForegroundColor Cyan
