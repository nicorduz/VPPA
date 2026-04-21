# VPPA Analyzer

Interactive tool to find the minimum VPPA strike price for a Solar + BESS portfolio. Built for the Lavender Solar (180 MWac, ERCOT) and Fairway BESS (120 MW / 240–480 MWh) projects under a flat-strike financial VPPA structure.

## Features

The app runs in two modes.

### Single-Year Analysis

Loads solar generation and ERCOT price data for one calendar year, runs a BESS dispatch optimization against a configurable VPPA block, and solves for the minimum strike price that delivers the required combined revenue. Outputs daily dispatch profiles, monthly volume breakdowns, a strike-sensitivity curve, and a full 8760 Excel export.

### Multi-Year Forecast Analysis

Solves for a single flat strike price that meets lifetime revenue requirements across the full contract duration, using forecast price data and a degraded TMY solar profile. Supports three optimization criteria selectable in the UI:

1. **Total sum**: cumulative margins across the contract must equal or exceed cumulative targets
2. **NPV**: discounted margins must equal or exceed discounted targets
3. **Worst year**: every individual year must meet its escalated target

The solver is closed-form. Annual margin is linear in strike, so each criterion reduces to a single equation. No numerical search runs.

Forecast mode handles solar degradation year-over-year, target escalation (inflation), and price extrapolation for years beyond the available forecast data.

## Project Structure

```
vppa-analyzer/
├── app.py                 # Streamlit UI, both modes
├── config.py              # Constants, defaults, color palette
├── data_loader.py         # Loads CSVs and validates hourly data
├── analysis_engine.py     # Dispatch model, strike solvers (single + multi-year)
├── visualizations.py      # Matplotlib charts
├── requirements.txt
└── data/
    ├── Lavender_PVsyst_P90.CSV
    ├── ERCOT_North_Hub_<year>.csv
    ├── Lavender_Node_<year>.csv
    └── Fairway_Node_<year>.csv
```

## Data Requirements

The app expects the following hourly CSV files in the `data/` folder:

- **Solar generation**: `Lavender_PVsyst_P90.CSV` — 8760-row TMY profile from PVsyst with a `solar_gen_mw` column
- **North Hub prices**: one file per forecast year (ERCOT North Hub LMP)
- **Lavender node prices**: one file per forecast year (Lavender POI LMP)
- **Fairway node prices**: one file per forecast year (Fairway POI LMP)

The exact filename pattern and parser logic live in `data_loader.py`. Modify that module if your file naming convention differs.

Each price file must contain 8760 hourly values (8784 on leap years is handled). Missing hours trigger validation errors in the UI.

## Key Parameters

### Lavender Solar
- 180 MWac / 225.54 MWdc
- VSUN 595W TOPCon modules
- Sungrow SG4400UD-MV-US inverters (46 units)
- Nextracker NX Horizon XTR
- POI: ERCOT, Brazos Electric transmission
- Expected COD: December 31, 2027

### Fairway BESS
- 120 MW power rating (fixed)
- 240 MWh (2-hour) or 480 MWh (4-hour) capacity
- Dispatch model charges at lowest-price hours, discharges during highest-price on-peak hours

### Amazon VPPA
- 15-year financial VPPA
- Settled at ERCOT North Hub
- **Flat strike, no escalator** across the full contract life
- Expected COD: December 31, 2027
- Guaranteed COD: June 30, 2028

## Model Logic

The dispatch model treats the VPPA block as an hourly delivery obligation during the configured on-peak window. Three sources fill the block in priority order:

1. **Solar generation** when available
2. **BESS discharge** when solar falls short (charged during lowest-price off-peak hours)
3. **Merchant purchase** from the market for any residual gap

Excess solar and BESS discharge outside the block window sell at merchant prices. Revenue = Strike + Basis (Node − Hub). Margin = VPPA Revenue + Merchant Sales Revenue − Market Purchase Cost − BESS Charging Cost.

In multi-year mode, the same dispatch logic runs once per contract year with solar production scaled by the degradation factor for that year. Prices shift year by year using the forecast data (or extrapolated values for years beyond the forecast horizon).

## Default Assumptions (Multi-Year Mode)

| Parameter | Default | Source |
|---|---|---|
| Contract duration | 15 years | Amazon VPPA |
| Contract start year | 2028 | First full year after Lavender COD |
| First-year degradation | 1.0% | PVsyst default for TOPCon LID/LETID |
| Annual degradation | 0.4%/year | PVsyst default for TOPCon |
| Lavender year-1 target | $20 M | Internal allocation |
| Fairway year-1 target | $20 M | Internal allocation |
| Target escalation | 2.5%/year | Long-term US CPI |
| Discount rate (NPV) | 8.0% | Typical project IRR hurdle |
| Price extrapolation | 2.0%/year | Beyond forecast horizon |

All defaults are editable in the sidebar.

## Outputs

### Single-Year Mode
- Daily dispatch profiles (summer and winter reference days)
- Volume breakdown (solar / BESS / merchant)
- BESS dispatch pattern and charge/discharge spreads
- Economics waterfall
- Strike-price sensitivity curve
- Monthly volume breakdown
- On-peak price comparison chart
- Excel export: Dashboard + Sensitivity + 8760 hourly data

### Multi-Year Mode
- Annual margin vs. escalated target (colored bars)
- Cumulative lifetime trajectory
- Annual economics stacked breakdown
- Lavender and Fairway pro-rata allocation per year
- Solar degradation curve with annual GWh delivery
- Price forecast trajectory (hub, node, basis) with extrapolated-year highlighting
- Annual block coverage mix (solar / BESS / merchant %)
- Multi-year strike sensitivity (undiscounted, NPV, years-meeting-target)
- Annual summary table
- Excel export: Dashboard + Annual Summary + Sensitivity + one 8760 tab per contract year

## License

Proprietary. Internal use at Blue Sky Utility / Nofar USA.

## Contact

Niko Orduz — Solar Energy Engineer, Blue Sky Utility / Nofar USA
