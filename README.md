# ☀️ Lavender + Fairway VPPA Analyzer

Interactive tool to find the minimum VPPA strike price needed to achieve target revenue requirements for the Lavender Solar + Fairway BESS bundled project.

## 🎯 What This Tool Does

Given your inputs:
- **VPPA Block Power** (e.g., 180 MW, 150 MW, 100 MW)
- **On-Peak Window** (e.g., 7 AM - 11 PM, or any custom window)
- **BESS Duration** (2-hour = 240 MWh, or 4-hour = 480 MWh)
- **Revenue Targets** (e.g., $20M for Lavender, $15M for Fairway)
- **Year** for historical price data

The tool calculates:
- **Minimum VPPA Strike Price** needed to meet combined revenue target
- **Dispatch Schedule** for BESS (when to charge/discharge)
- **Volume Breakdown** (Solar vs BESS vs Merchant purchases)
- **Daily Profiles** for summer and winter days
- **Sensitivity Analysis** showing margin at different strike prices

## 🚀 Quick Start

### 1. Install Python (if not already installed)

Download Python 3.9+ from [python.org](https://www.python.org/downloads/)

### 2. Set up the project

```bash
# Navigate to the project folder
cd lavender_vppa_analyzer

# Create a virtual environment (recommended)
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Add your data files

Create a `data` folder and add your CSV files:

```
lavender_vppa_analyzer/
├── app.py
├── data/                           # ← Create this folder
│   ├── Lavender_PVsyst_P90.CSV     # Solar generation profile
│   ├── ERCOT_LZ_NORTH_DA.csv       # North Hub prices
│   ├── LAVENDER_BENHUR_DA.csv      # Lavender node prices
│   └── FAIRWAY_FAIRFIELD_DA.csv    # Fairway node prices
├── ...
```

### 4. Run the application

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

## 📁 Data File Requirements

### Solar Generation File (`Lavender_PVsyst_P90.CSV`)

PVsyst output file with 8760 hourly values. Must contain:
- Column named `E_Grid` or `EArray` with generation in **kW**
- The tool automatically converts to MW

### Price Files

Each price file must have:
- 8760 rows (one per hour of year)
- Column containing `PRICE`, `LMP`, or `SPP` (case insensitive)
- Column containing `YEAR` for multi-year files
- Values in **$/MWh**

Example format:
```csv
DATE_TIME,DATE_YEAR,TIME_HOUR,ENERGY_PRICE
2024-01-01 00:00,2024,1,25.50
2024-01-01 01:00,2024,2,23.25
...
```

## 🔧 Configuration

Edit `config.py` to change:

```python
# File paths
DATA_DIR = "./data"  # Location of your data files

# Default parameters
DEFAULT_BLOCK_MW = 180
DEFAULT_START_HOUR = 7
DEFAULT_END_HOUR = 23

# Revenue targets (Lionel's numbers)
DEFAULT_LAVENDER_TARGET_M = 20.0  # $20M/year
DEFAULT_FAIRWAY_TARGET_M = 15.0   # $15M/year
```

## 📊 Understanding the Results

### Minimum Strike Price

The tool solves for the strike price using this equation:

```
Net Margin = VPPA Revenue - Costs
           = Block Volume × (Strike + Basis) - Market Costs - BESS Costs

Solving for Strike:
Strike_min = (Required Margin + Total Costs) / Block Volume - Avg Basis
```

### BESS Dispatch Algorithm

1. **Discharge**: During on-peak hours with gaps (solar < block), discharge to highest-priced hours first
2. **Charge**: During ANY hour of the day, charge during lowest-priced hours

This maximizes the spread between charge and discharge prices.

### Daily Profiles

- **Top Panel**: Stacked generation (solar + BESS discharge + merchant) with BESS charging shown as negative
- **Bottom Panel**: Price curves (Hub, Node, VPPA effective revenue)

## 📥 Excel Export

The export includes three sheets:

1. **Dashboard**: Summary of all parameters and key results
2. **Sensitivity Analysis**: Net margin at different strike prices
3. **8760 Data**: Complete hourly model including:
   - Solar generation
   - BESS charge/discharge schedule
   - Gap (merchant purchases)
   - All prices (Hub, Lavender node, Fairway node)
   - Basis calculations
   - VPPA revenue at the minimum strike price
   - All costs and net margin per hour

## 🔄 How Block Changes Affect BESS Dispatch

When you change the block parameters, the BESS dispatch is **completely recalculated**:

| Change | Effect on BESS |
|--------|----------------|
| Lower block MW | Smaller gaps → less discharge needed → less charging needed |
| Shorter time window | Fewer on-peak hours → different discharge hours selected |
| Different start/end hours | Different prices in window → different optimal dispatch |
| 4-hour vs 2-hour BESS | More energy available → can fill more gap hours |

## 🐛 Troubleshooting

### "Could not find energy column in solar file"
- Check that your PVsyst file has a column named `E_Grid` or similar
- Open the file and verify it has 8760 rows of data

### "Could not find price column"
- Price files need a column with `PRICE`, `LMP`, or `SPP` in the name
- Check for extra spaces in column headers

### Charts not displaying
- Make sure matplotlib is installed: `pip install matplotlib`
- Try restarting the Streamlit server

### Excel export fails
- Install openpyxl: `pip install openpyxl`

## 📂 Project Structure

```
lavender_vppa_analyzer/
├── app.py              # Main Streamlit application
├── analysis_engine.py  # Core dispatch and calculations
├── visualizations.py   # Chart generation functions
├── data_loader.py      # Data loading and validation
├── config.py           # Configuration and constants
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── data/               # Your input data files
```

## 🆓 Cost

This tool is **completely free** to run locally:
- Python: Free and open source
- Streamlit: Free for local use
- All libraries: Free and open source

No API keys, subscriptions, or cloud services required.

## 📝 Notes

- The model uses historical price data as a proxy for future prices
- BESS round-trip efficiency is set to 86%
- BESS availability factor is 98%
- One charge/discharge cycle per day assumed
- Solar is capped at AC capacity (180 MW)

## 🤝 Support

For questions about the model or Lavender/Fairway project specifics, contact the BSU engineering team.

---

*Built for Blue Sky Utility / Nofar USA*
