"""
Lavender + Fairway VPPA Analyzer - Configuration
Default parameters and constants
"""

# =============================================================================
# FILE PATHS (Update these to match your local data location)
# =============================================================================

# Base directory for data files
DATA_DIR = "./data"

# Input file names (will be joined with DATA_DIR)
SOLAR_FILE = "Lavender_PVsyst_P90.csv"
HUB_PRICE_FILE = "ERCOT_LZ_NORTH_DA.csv"
LAVENDER_NODE_FILE = "LAVENDER_BENHUR_DA.csv"
FAIRWAY_NODE_FILE = "FAIRWAY_FAIRFIELD_DA.csv"

# =============================================================================
# PROJECT PARAMETERS
# =============================================================================

# Lavender Solar
LAVENDER_CAPACITY_DC = 225.54  # MWdc
LAVENDER_CAPACITY_AC = 180.0   # MWac (inverter limit)

# Fairway BESS
BESS_POWER_MW = 120.0          # MW (fixed inverter capacity)
BESS_DURATION_2HR = 240.0      # MWh (2-hour configuration)
BESS_DURATION_4HR = 480.0      # MWh (4-hour configuration)
BESS_RTE = 0.86                # Round-trip efficiency
BESS_AVAILABILITY = 0.98       # Availability factor
BESS_CYCLES_PER_DAY = 1        # Maximum cycles per day

# =============================================================================
# DEFAULT ANALYSIS PARAMETERS
# =============================================================================

DEFAULT_BLOCK_MW = 180         # Default VPPA block size
DEFAULT_START_HOUR = 7         # Default on-peak start (7 AM)
DEFAULT_END_HOUR = 23          # Default on-peak end (11 PM)
DEFAULT_BESS_DURATION = "2-hour"
DEFAULT_YEAR = 2024

# Revenue targets (from Lionel)
DEFAULT_LAVENDER_TARGET_M = 20.0  # $20M/year
DEFAULT_FAIRWAY_TARGET_M = 15.0   # $15M/year

# =============================================================================
# VISUALIZATION
# =============================================================================

# Nofar brand colors
NOFAR_PURPLE = '#5B4FE9'
NOFAR_YELLOW = '#F5C118'
NOFAR_DARK = '#1a1a2e'

# Chart colors
SOLAR_YELLOW = '#FFD700'
BESS_GREEN = '#2ECC71'
BESS_CHARGE_BLUE = '#3498DB'
GAP_RED = '#E74C3C'
REVENUE_GREEN = '#27AE60'
COST_RED = '#C0392B'
MARGIN_BLUE = '#2980B9'
HUB_GRAY = '#7F8C8D'
NODE_ORANGE = '#E67E22'

# =============================================================================
# ANALYSIS SETTINGS
# =============================================================================

# Representative days for charts
SUMMER_DAY = 196  # July 15
WINTER_DAY = 15   # January 15

# Strike price sensitivity range
STRIKE_MIN = 40.0
STRIKE_MAX = 90.0
STRIKE_STEP = 2.5

# =============================================================================
# MULTI-YEAR FORECAST PARAMETERS
# =============================================================================

# Contract duration (Amazon VPPA = 15 years)
DEFAULT_CONTRACT_YEARS = 15

# Contract start year (Lavender expected COD is Dec 31, 2027; first full year 2028)
DEFAULT_CONTRACT_START_YEAR = 2028

# Solar degradation (PVsyst defaults for VSUN 595W TOPCon)
# PVsyst default note: for modern TOPCon, typical assumptions are ~1% first-year
# LID/LETID + ~0.4% annual thereafter. Always validate against the module datasheet
# linear warranty before finalizing.
DEFAULT_FIRST_YEAR_DEGRADATION = 0.010   # 1.0% first-year LID loss
DEFAULT_ANNUAL_DEGRADATION = 0.004       # 0.4% per year after year 1

# Revenue targets (flat $M in year 1 dollars, escalated by inflation)
DEFAULT_LAVENDER_YEAR1_TARGET_M = 20.0   # $20M/year (Lionel)
DEFAULT_FAIRWAY_YEAR1_TARGET_M = 20.0    # $20M/year (updated per Niko)

# Target escalation (applied to revenue target year-over-year)
DEFAULT_INFLATION_RATE = 0.025           # 2.5% annual (long-term US CPI assumption)

# Discount rate for NPV criterion
DEFAULT_DISCOUNT_RATE = 0.08             # 8% (typical project IRR hurdle)

# Price extension beyond available forecast years
DEFAULT_PRICE_EXTENSION_RATE = 0.02      # 2% per year (if forecast doesn't cover full contract)

# Optimization criterion options
CRITERION_TOTAL_SUM = "Total sum (undiscounted)"
CRITERION_NPV = "NPV (discounted)"
CRITERION_WORST_YEAR = "Every year (worst year binds)"

# Strike sensitivity range for multi-year
MULTIYEAR_STRIKE_MIN = 30.0
MULTIYEAR_STRIKE_MAX = 100.0
MULTIYEAR_STRIKE_STEP = 2.5

# Additional visualization colors for multi-year
DEGRADATION_COLOR = '#E74C3C'
FORECAST_HUB_COLOR = '#7F8C8D'
FORECAST_LAVENDER_COLOR = '#E67E22'
FORECAST_FAIRWAY_COLOR = '#3498DB'
TARGET_LINE_COLOR = '#5B4FE9'
CUMULATIVE_MARGIN_COLOR = '#27AE60'
CUMULATIVE_TARGET_COLOR = '#C0392B'
