# Configuration Audit Report

**Generated:** 2026-02-03  
**Purpose:** Identify redundant configuration files causing "hallucinations"

## Summary

Found **15 configuration files** in `user_data/`, many of which are redundant variations differing only in:

- Leverage settings
- Pair whitelists
- Stake amounts

## Redundant Files Identified

### Category 1: AroonMACD Backtest Configs (REDUNDANT)

These files are nearly identical except for leverage and minor pair ordering:

1. ✗ `config_aroon_300day_backtest.json` - 3x leverage, fixed stake
2. ✗ `config_aroon_300day_backtest_9x.json` - 6x leverage (despite name), unlimited stake
3. ✗ `config_aroon_momentum_engine.json` - 4x leverage, unlimited stake

**Recommendation:** DELETE - Replaced by `config_base.json` + strategic pipeline

### Category 2: Generic Backtest Configs (REDUNDANT)

4. ✗ `config_backtest_100.json` - Unknown purpose
2. ✗ `config_backtest_20tokens_shorts.json` - Shorts-specific config
3. ✗ `config_backtest_9x_top_tokens.json` - 9x leverage, 15 pairs
4. ✗ `config_backtest_300day_STANDARD.json` - Standard 300-day config

**Recommendation:** DELETE - Replaced by strategic pipeline with `-Pairs` parameter

### Category 3: Optimized Configs (REVIEW NEEDED)

8. ⚠ `config_aroonmacd_optimized.json` - May contain specific optimizations

**Recommendation:** REVIEW - Check if optimizations are in strategy file or config

### Category 4: Live Trading Configs (KEEP)

9. ✓ `config_live_trading_6x.json` - Active live trading config
2. ✓ `config_live_real.json` - Real trading config
3. ✓ `config_coindcx.json` - Exchange-specific config

**Recommendation:** KEEP - These are exchange/mode specific

### Category 5: Special Purpose Configs (KEEP)

12. ✓ `config.json` - Main config (legacy)
2. ✓ `config_api.json` - API-specific settings
3. ✓ `config_live_analysis.json` - Analysis mode
4. ✓ `config_solana.json` - Token-specific config

**Recommendation:** KEEP - Special purposes

## New File Structure

### ✅ Created Files

- `config_base.json` - **Single source of truth** for backtesting
- `config_runtime.json` - **Auto-generated** by strategic pipeline (temporary)

### 🔧 Strategic Pipeline Script

- `scripts/Run-Trading.ps1` - Unified automation script

## Migration Plan

### Phase 1: Immediate (DONE)

- ✅ Created `config_base.json`
- ✅ Created `scripts/Run-Trading.ps1`
- ✅ Created workflow documentation

### Phase 2: Cleanup (USER ACTION REQUIRED)

Move redundant configs to archive:

```powershell
# Create archive directory
New-Item -ItemType Directory -Path "c:\Users\USER\Desktop\Algotrading\user_data\config_archive" -Force

# Move redundant configs
Move-Item "c:\Users\USER\Desktop\Algotrading\user_data\config_aroon_300day_backtest.json" "c:\Users\USER\Desktop\Algotrading\user_data\config_archive\"
Move-Item "c:\Users\USER\Desktop\Algotrading\user_data\config_aroon_300day_backtest_9x.json" "c:\Users\USER\Desktop\Algotrading\user_data\config_archive\"
Move-Item "c:\Users\USER\Desktop\Algotrading\user_data\config_aroon_momentum_engine.json" "c:\Users\USER\Desktop\Algotrading\user_data\config_archive\"
Move-Item "c:\Users\USER\Desktop\Algotrading\user_data\config_backtest_100.json" "c:\Users\USER\Desktop\Algotrading\user_data\config_archive\"
Move-Item "c:\Users\USER\Desktop\Algotrading\user_data\config_backtest_20tokens_shorts.json" "c:\Users\USER\Desktop\Algotrading\user_data\config_archive\"
Move-Item "c:\Users\USER\Desktop\Algotrading\user_data\config_backtest_9x_top_tokens.json" "c:\Users\USER\Desktop\Algotrading\user_data\config_archive\"
Move-Item "c:\Users\USER\Desktop\Algotrading\user_data\config_backtest_300day_STANDARD.json" "c:\Users\USER\Desktop\Algotrading\user_data\config_archive\"
```

### Phase 3: Verification (NEXT STEP)

Test the strategic pipeline with a short backtest:

```powershell
cd c:\Users\USER\Desktop\Algotrading
.\scripts\Run-Trading.ps1 -Mode backtest -Days 5 -Leverage 6
```

## Benefits of New System

| Old System | New System |
|------------|------------|
| 15+ config files | 1 base config |
| Manual file creation | Automated generation |
| Easy to make mistakes | Parameter-driven |
| Hard to track changes | Single source of truth |
| Cluttered workspace | Clean structure |

## Usage Examples

```powershell
# Quick 7-day backtest
.\scripts\Run-Trading.ps1 -Mode backtest -Days 7 -Leverage 6

# 300-day backtest with 9x leverage
.\scripts\Run-Trading.ps1 -Mode backtest -Days 300 -Leverage 9

# Custom pairs
.\scripts\Run-Trading.ps1 -Mode backtest -Days 30 -Pairs "SOL/USDT:USDT,XRP/USDT:USDT"

# Different strategy
.\scripts\Run-Trading.ps1 -Mode backtest -Strategy VWAPDMIStrategy -Days 100 -Leverage 5
```

## Next Steps

1. ✅ Review this audit report
2. ⏳ Test the strategic pipeline (5-day backtest)
3. ⏳ Archive redundant config files
4. ⏳ Update any existing scripts to use new pipeline
