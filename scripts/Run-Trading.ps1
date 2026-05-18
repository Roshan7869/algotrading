<#
.SYNOPSIS
    Strategic Pipeline for Freqtrade - Unified Backtesting and Trading Script

.DESCRIPTION
    This script provides a simplified, sequential pipeline for backtesting and trading.
    It eliminates the need to create multiple config files by dynamically generating
    runtime configurations based on user parameters.

.PARAMETER Mode
    Operation mode: 'backtest', 'dry-run', or 'live'

.PARAMETER Strategy
    Strategy name (without .py extension). Default: AroonMomentumEngine_Hybrid

.PARAMETER Days
    Number of days to backtest (for backtest mode only). Default: 300

.PARAMETER Leverage
    Leverage multiplier to apply. Default: 6

.PARAMETER StakeAmount
    Initial capital in USDT. Default: 1000

.PARAMETER Pairs
    Comma-separated list of trading pairs (e.g., "SOL/USDT:USDT,XRP/USDT:USDT")
    If not specified, uses default pairs from config_base.json

.EXAMPLE
    .\Run-Trading.ps1 -Mode backtest -Days 7 -Leverage 6
    
.EXAMPLE
    .\Run-Trading.ps1 -Mode backtest -Strategy AroonMomentumEngine_Hybrid -Days 300 -Leverage 9 -Pairs "SOL/USDT:USDT,DOGE/USDT:USDT,XRP/USDT:USDT"
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('backtest', 'dry-run', 'live')]
    [string]$Mode,
    
    [Parameter(Mandatory = $false)]
    [string]$Strategy = "AroonMomentumEngine_Hybrid",
    
    [Parameter(Mandatory = $false)]
    [int]$Days = 300,
    
    [Parameter(Mandatory = $false)]
    [double]$Leverage = 6.0,
    
    [Parameter(Mandatory = $false)]
    [int]$StakeAmount = 1000,
    
    [Parameter(Mandatory = $false)]
    [string]$Pairs = ""
)

# Color output functions
function Write-Success { 
    param([string]$Message) 
    Write-Host "[OK] $Message" -ForegroundColor Green 
}
function Write-InfoMsg { 
    param([string]$Message) 
    Write-Host "[INFO] $Message" -ForegroundColor Cyan 
}
function Write-WarningMsg { 
    param([string]$Message) 
    Write-Host "[WARN] $Message" -ForegroundColor Yellow 
}
function Write-ErrorMsg { 
    param([string]$Message) 
    Write-Host "[ERROR] $Message" -ForegroundColor Red 
}

# Configuration
$ProjectRoot = "c:\Users\USER\Desktop\Algotrading"
$BaseConfigPath = "$ProjectRoot\user_data\config_base.json"
$RuntimeConfigPath = "$ProjectRoot\user_data\config_runtime.json"
$ResultsDir = "$ProjectRoot\user_data\backtest_results"

Write-InfoMsg "═══════════════════════════════════════════════════════════"
Write-InfoMsg "  Freqtrade Strategic Pipeline"
Write-InfoMsg "═══════════════════════════════════════════════════════════"
Write-InfoMsg "Mode: $Mode"
Write-InfoMsg "Strategy: $Strategy"
if ($Mode -eq 'backtest') {
    Write-InfoMsg "Days: $Days"
}
Write-InfoMsg "Leverage: ${Leverage}x"
Write-InfoMsg "Stake Amount: $StakeAmount USDT"
Write-InfoMsg "═══════════════════════════════════════════════════════════"

# Step 1: Validate base config exists
if (-not (Test-Path $BaseConfigPath)) {
    Write-ErrorMsg "Base config not found at: $BaseConfigPath"
    exit 1
}
Write-Success "Base config found"

# Step 2: Load base config
try {
    $baseConfig = Get-Content $BaseConfigPath -Raw | ConvertFrom-Json
    Write-Success "Base config loaded"
}
catch {
    Write-ErrorMsg "Failed to parse base config: $_"
    exit 1
}

# Step 3: Apply runtime modifications
if (-not ($baseConfig.PSObject.Properties.Name -contains 'strategy')) {
    $baseConfig | Add-Member -MemberType NoteProperty -Name "strategy" -Value $Strategy
}
else {
    $baseConfig.strategy = $Strategy
}
$baseConfig.dry_run_wallet = $StakeAmount
$baseConfig.bot_name = "${Strategy}_${Leverage}x_${Mode}"

# Apply leverage using the params structure (Freqtrade standard)
if (-not ($baseConfig.PSObject.Properties.Name -contains 'params')) {
    $baseConfig | Add-Member -MemberType NoteProperty -Name "params" -Value @{}
}
if (-not ($baseConfig.params.PSObject.Properties.Name -contains $Strategy)) {
    $baseConfig.params | Add-Member -MemberType NoteProperty -Name $Strategy -Value @{}
}
if (-not ($baseConfig.params.$Strategy.PSObject.Properties.Name -contains 'buy')) {
    $baseConfig.params.$Strategy | Add-Member -MemberType NoteProperty -Name "buy" -Value @{}
}
$baseConfig.params.$Strategy.buy.leverage_multiplier = $Leverage

# Override pairs if specified
if ($Pairs -ne "") {
    $pairArray = $Pairs -split ',' | ForEach-Object { $_.Trim() }
    $baseConfig.exchange.pair_whitelist = $pairArray
    Write-InfoMsg "Using custom pairs: $Pairs"
}

# Set mode-specific settings
switch ($Mode) {
    'backtest' {
        $baseConfig.dry_run = $true
    }
    'dry-run' {
        $baseConfig.dry_run = $true
    }
    'live' {
        $baseConfig.dry_run = $false
        Write-WarningMsg "LIVE MODE - Real funds will be used!"
        $confirmation = Read-Host "Type 'CONFIRM' to proceed with live trading"
        if ($confirmation -ne 'CONFIRM') {
            Write-ErrorMsg "Live trading cancelled"
            exit 1
        }
    }
}

# Step 4: Save runtime config
try {
    $baseConfig | ConvertTo-Json -Depth 10 | Set-Content $RuntimeConfigPath
    Write-Success "Runtime config generated: $RuntimeConfigPath"
}
catch {
    Write-ErrorMsg "Failed to save runtime config: $_"
    exit 1
}

# Step 5: Calculate timerange for backtest
$timerangeArg = ""
if ($Mode -eq 'backtest') {
    $endDate = Get-Date
    $startDate = $endDate.AddDays(-$Days)
    $timerange = "{0}-{1}" -f $startDate.ToString("yyyyMMdd"), $endDate.ToString("yyyyMMdd")
    Write-InfoMsg "Timerange: $($startDate.ToString('yyyy-MM-dd')) to $($endDate.ToString('yyyy-MM-dd'))"
}

# Step 6: Ensure results directory exists
if (-not (Test-Path $ResultsDir)) {
    New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null
    Write-Success "Created results directory"
}

# Step 7: Download data if in backtest mode
if ($Mode -eq 'backtest') {
    Write-InfoMsg "═══════════════════════════════════════════════════════════"
    Write-InfoMsg "Downloading historical data..."
    Write-InfoMsg "═══════════════════════════════════════════════════════════"
    
    $pairsToDownload = $baseConfig.exchange.pair_whitelist
    
    foreach ($pair in $pairsToDownload) {
        Write-InfoMsg "Downloading data for $pair..."
        
        docker run --rm `
            -v "${PWD}/user_data:/freqtrade/user_data" `
            freqtradeorg/freqtrade:stable `
            download-data `
            --config /freqtrade/user_data/config_runtime.json `
            --pairs $pair `
            --timeframes 1h `
            --timerange $timerange `
            --exchange binance `
            --trading-mode futures
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Downloaded $pair"
        }
        else {
            Write-WarningMsg "Failed to download $pair (may already exist)"
        }
    }
    Write-InfoMsg ""
}

# Step 8: Execute Freqtrade command
Write-InfoMsg "═══════════════════════════════════════════════════════════"
Write-InfoMsg "Executing Freqtrade..."
Write-InfoMsg "═══════════════════════════════════════════════════════════"

try {
    switch ($Mode) {
        'backtest' {
            $exportFilename = "backtest_${Strategy}_${Leverage}x_${Days}days.json"
            
            Write-InfoMsg "Running backtest..."
            docker run --rm `
                -v "${PWD}/user_data:/freqtrade/user_data" `
                freqtradeorg/freqtrade:stable `
                backtesting `
                --config /freqtrade/user_data/config_runtime.json `
                --strategy $Strategy `
                --timeframe 1h `
                --timerange $timerange `
                --export trades `
                --export-filename "/freqtrade/user_data/backtest_results/$exportFilename" `
                --breakdown day `
                --cache none
        }
        'dry-run' {
            Write-InfoMsg "Starting dry-run mode..."
            docker run --rm `
                -v "${PWD}/user_data:/freqtrade/user_data" `
                freqtradeorg/freqtrade:stable `
                trade `
                --config /freqtrade/user_data/config_runtime.json `
                --strategy $Strategy
        }
        'live' {
            Write-InfoMsg "Starting LIVE trading mode..."
            docker run --rm `
                -v "${PWD}/user_data:/freqtrade/user_data" `
                freqtradeorg/freqtrade:stable `
                trade `
                --config /freqtrade/user_data/config_runtime.json `
                --strategy $Strategy
        }
    }
    
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -eq 0) {
        Write-Success "═══════════════════════════════════════════════════════════"
        Write-Success "  Execution completed successfully!"
        Write-Success "═══════════════════════════════════════════════════════════"
        
        if ($Mode -eq 'backtest') {
            Write-InfoMsg ""
            Write-InfoMsg "Results saved to: $ResultsDir\$exportFilename"
            Write-InfoMsg ""
            Write-InfoMsg "To view results:"
            Write-InfoMsg "  - Check user_data/backtest_results/"
            Write-InfoMsg "  - Review the exported trades file"
        }
    }
    else {
        Write-ErrorMsg "═══════════════════════════════════════════════════════════"
        Write-ErrorMsg "  Execution failed with exit code: $exitCode"
        Write-ErrorMsg "═══════════════════════════════════════════════════════════"
    }
}
catch {
    Write-ErrorMsg "Failed to execute Freqtrade: $_"
    exit 1
}

# Step 9: Cleanup (optional - keep runtime config for debugging)
# Remove-Item $RuntimeConfigPath -ErrorAction SilentlyContinue
Write-InfoMsg ""
Write-InfoMsg "Runtime config preserved at: $RuntimeConfigPath"
Write-InfoMsg "Script completed."
