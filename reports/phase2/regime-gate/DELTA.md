# Regime-gate DELTA — does the Wasserstein paper help OUR trades?

| Slice | Strategy | Variant | Trades | Exp/trade % | Win % | PF | Σ profit (abs, fixed stake) | MaxDD (abs) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| validation | EmaTrendFollowing | baseline (all) | 529 | -0.925 | 39.5 | 0.714 | -10842.2 | 14083.8 |
| validation | EmaTrendFollowing | gate=calm-only | 453 | -0.648 | 42.2 | 0.790 | -6294.4 | 10108.0 |
| validation | EmaTrendFollowing | gate=volatile-only | 76 | -2.582 | 23.7 | 0.378 | -4547.8 | 4402.6 |
| validation | AroonMomentumEngine_V2 | baseline (all) | 2029 | -0.863 | 40.7 | 0.622 | -26986.8 | 29454.9 |
| validation | AroonMomentumEngine_V2 | gate=calm-only | 1510 | -0.862 | 40.5 | 0.609 | -21057.7 | 23533.3 |
| validation | AroonMomentumEngine_V2 | gate=volatile-only | 519 | -0.866 | 41.0 | 0.655 | -5929.1 | 6071.2 |
| validation | BollingerMeanReversion | baseline (all) | 72 | -0.983 | 40.3 | 0.624 | -1650.7 | 2936.7 |
| validation | BollingerMeanReversion | gate=calm-only | 65 | -0.919 | 40.0 | 0.640 | -1359.8 | 2838.3 |
| validation | BollingerMeanReversion | gate=volatile-only | 7 | -1.577 | 42.9 | 0.504 | -291.0 | 187.7 |

## Gate quality (validation slice)

| Strategy | Kept (calm) exp% | Blocked (volatile) exp% | Delta if blocked removed (pp) |
|---|---:|---:|---:|
| EmaTrendFollowing | -0.648 | -2.582 | **+0.278** |
| AroonMomentumEngine_V2 | -0.862 | -0.866 | **+0.001** |
| BollingerMeanReversion | -0.919 | -1.577 | **+0.064** |
