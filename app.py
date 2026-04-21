"""
Lavender + Fairway VPPA Analyzer
Interactive tool to find minimum VPPA strike price for target revenues

Supports two modes:
1. Single Year  - Original analysis for a single calendar year
2. Multi-Year Forecast - Flat strike that meets lifetime revenue requirements
                         across the full contract duration, using forecast
                         price data and TMY solar with configurable degradation

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import os
from datetime import datetime

# Import our modules
from config import (
    DEFAULT_BLOCK_MW, DEFAULT_START_HOUR, DEFAULT_END_HOUR,
    DEFAULT_LAVENDER_TARGET_M, DEFAULT_FAIRWAY_TARGET_M,
    BESS_POWER_MW, BESS_DURATION_2HR, BESS_DURATION_4HR,
    SUMMER_DAY, WINTER_DAY, NOFAR_PURPLE,
    # Multi-year constants
    DEFAULT_CONTRACT_YEARS, DEFAULT_CONTRACT_START_YEAR,
    DEFAULT_FIRST_YEAR_DEGRADATION, DEFAULT_ANNUAL_DEGRADATION,
    DEFAULT_LAVENDER_YEAR1_TARGET_M, DEFAULT_FAIRWAY_YEAR1_TARGET_M,
    DEFAULT_INFLATION_RATE, DEFAULT_DISCOUNT_RATE,
    DEFAULT_PRICE_EXTENSION_RATE,
    CRITERION_TOTAL_SUM, CRITERION_NPV, CRITERION_WORST_YEAR,
    MULTIYEAR_STRIKE_MIN, MULTIYEAR_STRIKE_MAX, MULTIYEAR_STRIKE_STEP,
)
from vpp_data_loader import load_all_data, get_available_years, validate_data
from analysis_engine import (
    run_dispatch_model, calculate_min_strike, calculate_margin_at_strike,
    calculate_vppa_revenue_at_strike, run_sensitivity_analysis,
    allocate_margin_to_projects, prepare_export_data, create_summary_df,
    # Multi-year functions
    find_min_strike_multiyear, multiyear_summary_at_strike, multiyear_sensitivity,
    compute_degradation_factor, apply_degradation_to_solar, escalate_price_array,
)
from visualizations import (
    plot_daily_profile, plot_sensitivity_curve, plot_volume_breakdown,
    plot_bess_dispatch_pattern, plot_economics_waterfall,
    plot_monthly_breakdown, plot_price_comparison,
    # Multi-year plots
    plot_annual_margin_vs_target, plot_cumulative_trajectory,
    plot_annual_economics_stacked, plot_solar_degradation,
    plot_price_forecast_trajectory, plot_multiyear_sensitivity,
    plot_volume_mix_by_year, plot_project_allocation_trajectory,
)


# =============================================================================
# PAGE CONFIGURATION
# =============================================================================
st.set_page_config(
    page_title="Lavender + Fairway VPPA Analyzer",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(f"""
<style>
    .main-header {{
        color: {NOFAR_PURPLE};
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }}
    .sub-header {{
        color: #666;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }}
    .metric-card {{
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        border-left: 4px solid {NOFAR_PURPLE};
    }}
    .success-box {{
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
    }}
    .warning-box {{
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }}
    .stButton>button {{
        background-color: {NOFAR_PURPLE};
        color: white;
    }}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# HEADER
# =============================================================================
st.markdown('<p class="main-header">☀️ Lavender + Fairway VPPA Analyzer</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Interactive tool to find minimum VPPA strike price for target revenues</p>', unsafe_allow_html=True)


# =============================================================================
# SIDEBAR: MODE SELECTOR
# =============================================================================
with st.sidebar:
    st.header("🎛️ Analysis Mode")
    mode = st.radio(
        "Select analysis mode",
        options=["Single Year", "Multi-Year Forecast"],
        index=1,
        help=(
            "Single Year: Original single-year analysis.\n\n"
            "Multi-Year Forecast: Solve for a flat strike across the full contract "
            "life using forecast price data and degraded TMY solar."
        ),
    )
    st.divider()


# =============================================================================
# MODE 1: SINGLE YEAR (ORIGINAL BEHAVIOR - UNCHANGED)
# =============================================================================
if mode == "Single Year":

    with st.sidebar:
        st.header("📊 Analysis Parameters")

        st.subheader("📅 Year Selection")
        available_years = get_available_years()
        year = st.selectbox(
            "Analysis Year",
            options=available_years,
            index=available_years.index(2024) if 2024 in available_years else 0,
            help="Select the year for price data"
        )

        st.divider()

        st.subheader("⚡ VPPA Block Configuration")
        block_mw = st.slider(
            "Block Power (MW)",
            min_value=50, max_value=200, value=DEFAULT_BLOCK_MW, step=10,
        )
        col1, col2 = st.columns(2)
        with col1:
            start_hour = st.selectbox(
                "Start Hour", options=list(range(0, 24)),
                index=DEFAULT_START_HOUR, format_func=lambda x: f"{x:02d}:00",
            )
        with col2:
            end_hour = st.selectbox(
                "End Hour", options=list(range(1, 25)),
                index=DEFAULT_END_HOUR - 1, format_func=lambda x: f"{x:02d}:00",
            )

        block_hours = end_hour - start_hour
        if block_hours <= 0:
            st.error("End hour must be after start hour!")
            block_hours = 1
        else:
            st.info(f"**Block Duration: {block_hours} hours/day**")

        st.divider()

        st.subheader("🔋 BESS Configuration (Fairway)")
        bess_duration = st.radio(
            "BESS Duration",
            options=["2-hour (240 MWh)", "4-hour (480 MWh)"],
            index=0,
        )
        bess_mwh = BESS_DURATION_2HR if "2-hour" in bess_duration else BESS_DURATION_4HR
        st.caption(f"Power Rating: **{BESS_POWER_MW:.0f} MW** (fixed)")

        st.divider()

        st.subheader("💰 Revenue Requirements")
        lavender_target = st.number_input(
            "Lavender Min Revenue ($M/year)",
            min_value=0.0, max_value=100.0,
            value=DEFAULT_LAVENDER_TARGET_M, step=1.0,
        )
        fairway_target = st.number_input(
            "Fairway Min Revenue ($M/year)",
            min_value=0.0, max_value=100.0,
            value=DEFAULT_FAIRWAY_TARGET_M, step=1.0,
        )
        combined_target = lavender_target + fairway_target
        st.metric("Combined Target", f"${combined_target:.1f} M/year")

        st.divider()
        run_analysis = st.button(
            "🔄 Run Analysis", type="primary", use_container_width=True,
        )

    # ---- MAIN PANEL - SINGLE YEAR ----
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'min_strike' not in st.session_state:
        st.session_state.min_strike = None

    if run_analysis:
        with st.spinner("Loading data and running dispatch optimization..."):
            try:
                solar_df, hub_prices, lavender_prices, fairway_prices = load_all_data(year)
                validation = validate_data(solar_df, hub_prices, lavender_prices, fairway_prices)
                if not validation['valid']:
                    for error in validation['errors']:
                        st.error(error)
                    st.stop()
                for warning in validation['warnings']:
                    st.warning(warning)

                results = run_dispatch_model(
                    solar_df=solar_df, hub_prices=hub_prices,
                    lavender_prices=lavender_prices, fairway_prices=fairway_prices,
                    block_mw=block_mw, start_hour=start_hour, end_hour=end_hour,
                    bess_mwh=bess_mwh, bess_mw=BESS_POWER_MW,
                )

                required_margin = combined_target * 1e6
                min_strike = calculate_min_strike(results, required_margin)

                st.session_state.results = results
                st.session_state.min_strike = min_strike
                st.session_state.year = year
                st.session_state.lavender_target = lavender_target
                st.session_state.fairway_target = fairway_target
                st.session_state.combined_target = combined_target
            except Exception as e:
                st.error(f"Error running analysis: {str(e)}")
                st.exception(e)
                st.stop()

    if st.session_state.results is not None:
        results = st.session_state.results
        min_strike = st.session_state.min_strike
        year = st.session_state.year
        lavender_target = st.session_state.lavender_target
        fairway_target = st.session_state.fairway_target
        combined_target = st.session_state.combined_target

        st.markdown(f"""
        <div class="success-box">
            <h2 style="color: #155724; margin-bottom: 0.5rem;">🎯 Minimum VPPA Strike Price</h2>
            <h1 style="color: {NOFAR_PURPLE}; font-size: 3rem; margin: 0;">${min_strike:.2f} /MWh</h1>
            <p style="color: #155724; margin-top: 0.5rem;">To achieve ${combined_target:.1f}M combined annual revenue ({year} price data)</p>
        </div>
        """, unsafe_allow_html=True)

        st.subheader("📊 Key Metrics")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Block Volume", f"{results['block_volume']/1e6:.2f} TWh")
        with col2: st.metric("Solar Coverage", f"{results['solar_pct']:.1f}%")
        with col3: st.metric("BESS Coverage", f"{results['bess_pct']:.1f}%")
        with col4: st.metric("Merchant Required", f"{results['merchant_pct']:.1f}%")

        st.subheader("📈 Daily Profiles")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Summer Day (July 15)**")
            fig_summer = plot_daily_profile(
                results['model'], day=SUMMER_DAY, block_mw=results['block_mw'],
                strike_price=min_strike, title_suffix="- Summer (July 15)",
            )
            st.pyplot(fig_summer)
        with col2:
            st.markdown("**Winter Day (January 15)**")
            fig_winter = plot_daily_profile(
                results['model'], day=WINTER_DAY, block_mw=results['block_mw'],
                strike_price=min_strike, title_suffix="- Winter (January 15)",
            )
            st.pyplot(fig_winter)

        st.subheader("💰 Economics Summary")
        col1, col2 = st.columns([2, 1])
        with col1:
            vppa_revenue = calculate_vppa_revenue_at_strike(results, min_strike)
            net_margin = calculate_margin_at_strike(results, min_strike)
            allocation = allocate_margin_to_projects(net_margin, lavender_target * 1e6, fairway_target * 1e6)

            economics_df = pd.DataFrame({
                'Metric': [
                    '📊 VOLUME BREAKDOWN', 'Total Block Volume', 'Solar Contribution',
                    'BESS Contribution', 'Merchant Purchase',
                    'Solar Excess Sold Merchant', 'BESS Excess Sold Merchant', '',
                    f'💵 ECONOMICS (at ${min_strike:.2f}/MWh)',
                    'VPPA Revenue', 'Merchant Revenue',
                    '  - Solar Excess Revenue', '  - BESS Excess Revenue',
                    'Market Purchase Cost', 'BESS Charging Cost',
                    'Total Costs', 'Net Margin', '',
                    '🏭 PROJECT ALLOCATION', 'Lavender Margin', 'Fairway Margin',
                ],
                'Value': [
                    '',
                    f"{results['block_volume']:,.0f} MWh",
                    f"{results['solar_mwh']:,.0f} MWh ({results['solar_pct']:.1f}%)",
                    f"{results['bess_mwh']:,.0f} MWh ({results['bess_pct']:.1f}%)",
                    f"{results['merchant_mwh']:,.0f} MWh ({results['merchant_pct']:.1f}%)",
                    f"{results.get('solar_excess_mwh', 0):,.0f} MWh",
                    f"{results.get('bess_excess_mwh', 0):,.0f} MWh",
                    '', '',
                    f"${vppa_revenue/1e6:.2f} M",
                    f"${results.get('merchant_sales_revenue', 0)/1e6:.2f} M",
                    f"${results.get('solar_excess_revenue', 0)/1e6:.2f} M",
                    f"${results.get('bess_excess_revenue', 0)/1e6:.2f} M",
                    f"${results['market_cost']/1e6:.2f} M",
                    f"${results['bess_charge_cost']/1e6:.2f} M",
                    f"${results['total_costs']/1e6:.2f} M",
                    f"${net_margin/1e6:.2f} M ✓",
                    '', '',
                    f"${allocation['lavender_margin']/1e6:.2f} M {'✓' if allocation['lavender_met'] else '✗'}",
                    f"${allocation['fairway_margin']/1e6:.2f} M {'✓' if allocation['fairway_met'] else '✗'}",
                ]
            })
            st.dataframe(economics_df, hide_index=True, use_container_width=True)
        with col2:
            fig_volume = plot_volume_breakdown(results)
            st.pyplot(fig_volume)

        st.subheader("🔋 BESS Performance")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Avg Charge Price", f"${results['avg_charge_price']:.2f}/MWh")
        with col2: st.metric("Avg Discharge Price", f"${results['avg_discharge_price']:.2f}/MWh")
        with col3: st.metric("BESS Spread", f"${results['bess_spread_per_mwh']:.2f}/MWh")
        with col4: st.metric("Off-Peak Charging", f"{results['off_peak_charge_pct']:.1f}%")

        st.subheader("💸 Merchant Excess Sales")
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Solar Excess Sold", f"{results['solar_excess_mwh']/1000:.1f} GWh")
        with c2: st.metric("Merchant Sales Revenue", f"${results['merchant_sales_revenue']/1e6:.2f} M")
        with c3: st.metric("BESS Excess Sold", f"{results['bess_excess_mwh']/1000:.1f} GWh")

        col1, col2 = st.columns(2)
        with col1:
            fig_bess = plot_bess_dispatch_pattern(results['model'])
            st.pyplot(fig_bess)
        with col2:
            fig_waterfall = plot_economics_waterfall(results, min_strike)
            st.pyplot(fig_waterfall)

        st.subheader("📉 Strike Price Sensitivity")
        fig_sensitivity = plot_sensitivity_curve(results, min_strike, combined_target * 1e6)
        st.pyplot(fig_sensitivity)

        with st.expander("View Sensitivity Data Table"):
            sensitivity_df = run_sensitivity_analysis(results)
            sensitivity_df['vppa_revenue'] = sensitivity_df['vppa_revenue'].apply(lambda x: f"${x/1e6:.2f}M")
            sensitivity_df['net_margin'] = sensitivity_df['net_margin'].apply(lambda x: f"${x/1e6:.2f}M")
            sensitivity_df['margin_per_mwh'] = sensitivity_df['margin_per_mwh'].apply(lambda x: f"${x:.2f}")
            sensitivity_df['strike_price'] = sensitivity_df['strike_price'].apply(lambda x: f"${x:.2f}")
            st.dataframe(sensitivity_df, hide_index=True, use_container_width=True)

        with st.expander("📊 Additional Charts"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Monthly Volume Breakdown**")
                fig_monthly = plot_monthly_breakdown(results['model'])
                st.pyplot(fig_monthly)
            with col2:
                st.markdown("**On-Peak Price Comparison**")
                fig_prices = plot_price_comparison(results['model'])
                st.pyplot(fig_prices)

        st.divider()
        st.subheader("📥 Export Results")
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("""
            Export includes:
            - **Dashboard**: Summary of all parameters and results
            - **Sensitivity Analysis**: Margin at different strike prices
            - **8760 Hourly Data**: Complete hourly model with dispatch results and economics
            """)
        with col2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                summary_df = create_summary_df(results, min_strike, year, lavender_target, fairway_target)
                summary_df.to_excel(writer, sheet_name='Dashboard', index=False)
                sensitivity_df = run_sensitivity_analysis(results)
                sensitivity_df.to_excel(writer, sheet_name='Sensitivity Analysis', index=False)
                export_df = prepare_export_data(results, min_strike, year, lavender_target, fairway_target)
                export_df.to_excel(writer, sheet_name=f'8760 Data {year}', index=False)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"Lavender_Fairway_Analysis_{year}_{block_mw}MW_{block_hours}hr_{timestamp}.xlsx"
            st.download_button(
                label="📥 Download Excel Report",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", use_container_width=True,
            )
    else:
        st.info("""
        👈 **Configure your analysis parameters in the sidebar, then click "Run Analysis"**

        This tool will:
        1. Load solar generation and price data for the selected year
        2. Run BESS dispatch optimization based on your block configuration
        3. Calculate the minimum VPPA strike price needed to meet your revenue targets
        4. Generate daily profiles and sensitivity analysis
        5. Allow you to export all results to Excel
        """)


# =============================================================================
# MODE 2: MULTI-YEAR FORECAST
# =============================================================================
else:

    with st.sidebar:
        st.header("📊 Contract Parameters")

        available_years = get_available_years()
        max_available = max(available_years)
        min_available = min(available_years)

        st.subheader("📅 Contract Horizon")
        contract_start = st.number_input(
            "Contract Start Year",
            min_value=int(min_available), max_value=int(max_available) + 20,
            value=DEFAULT_CONTRACT_START_YEAR, step=1,
            help="First year of the VPPA contract. Lavender expected COD: Dec 31, 2027.",
        )
        contract_years_n = st.number_input(
            "Contract Duration (years)",
            min_value=1, max_value=30,
            value=DEFAULT_CONTRACT_YEARS, step=1,
            help="Amazon VPPA = 15 years.",
        )

        contract_end = contract_start + contract_years_n - 1
        st.caption(f"Contract period: **{contract_start}–{contract_end}**")

        if contract_end > max_available:
            missing = contract_end - max_available
            st.warning(
                f"⚠️ Forecast data available through {max_available}. "
                f"Prices for the last {missing} year(s) will be extrapolated."
            )

        st.divider()

        st.subheader("⚡ VPPA Block Configuration")
        block_mw = st.slider(
            "Block Power (MW)",
            min_value=50, max_value=200, value=DEFAULT_BLOCK_MW, step=10,
        )
        col1, col2 = st.columns(2)
        with col1:
            start_hour = st.selectbox(
                "Start Hour", options=list(range(0, 24)),
                index=DEFAULT_START_HOUR, format_func=lambda x: f"{x:02d}:00",
                key="my_start",
            )
        with col2:
            end_hour = st.selectbox(
                "End Hour", options=list(range(1, 25)),
                index=DEFAULT_END_HOUR - 1, format_func=lambda x: f"{x:02d}:00",
                key="my_end",
            )
        block_hours = end_hour - start_hour
        if block_hours <= 0:
            st.error("End hour must be after start hour!")
            block_hours = 1
        else:
            st.info(f"**Block Duration: {block_hours} hours/day**")

        st.divider()

        st.subheader("🔋 BESS Configuration (Fairway)")
        bess_duration = st.radio(
            "BESS Duration",
            options=["2-hour (240 MWh)", "4-hour (480 MWh)"],
            index=0, key="my_bess",
        )
        bess_mwh = BESS_DURATION_2HR if "2-hour" in bess_duration else BESS_DURATION_4HR
        st.caption(f"Power Rating: **{BESS_POWER_MW:.0f} MW** (fixed)")

        st.divider()

        st.subheader("☀️ Solar Degradation")
        st.caption(
            "ℹ️ **PVsyst defaults for TOPCon modules**: ~1.0% first-year LID/LETID + ~0.4%/year "
            "thereafter. Validate against VSUN 595W linear warranty before finalizing."
        )
        first_year_deg_pct = st.number_input(
            "First-Year Degradation (%)",
            min_value=0.0, max_value=5.0,
            value=DEFAULT_FIRST_YEAR_DEGRADATION * 100,
            step=0.1, format="%.2f",
            help="Initial LID/LETID loss applied to year 1.",
        )
        annual_deg_pct = st.number_input(
            "Annual Degradation after Year 1 (%)",
            min_value=0.0, max_value=2.0,
            value=DEFAULT_ANNUAL_DEGRADATION * 100,
            step=0.05, format="%.2f",
            help="Compounded year-over-year degradation from year 2 onwards.",
        )
        first_year_deg = first_year_deg_pct / 100.0
        annual_deg = annual_deg_pct / 100.0

        last_deg = compute_degradation_factor(contract_years_n, first_year_deg, annual_deg) * 100
        st.caption(f"Last-year capacity factor: **{last_deg:.2f}%** of nameplate")

        st.divider()

        st.subheader("💰 Revenue Requirements (Year 1 dollars)")
        lav_year1_target = st.number_input(
            "Lavender Revenue (Year 1, $M)",
            min_value=0.0, max_value=200.0,
            value=DEFAULT_LAVENDER_YEAR1_TARGET_M, step=1.0,
        )
        fair_year1_target = st.number_input(
            "Fairway Revenue (Year 1, $M)",
            min_value=0.0, max_value=200.0,
            value=DEFAULT_FAIRWAY_YEAR1_TARGET_M, step=1.0,
        )

        inflation_pct = st.number_input(
            "Target Escalation Rate (% / year)",
            min_value=0.0, max_value=10.0,
            value=DEFAULT_INFLATION_RATE * 100,
            step=0.1, format="%.2f",
            help="Inflation applied to annual revenue targets (Amazon strike has NO escalator).",
        )
        inflation_rate = inflation_pct / 100.0

        lav_last = lav_year1_target * ((1 + inflation_rate) ** (contract_years_n - 1))
        fair_last = fair_year1_target * ((1 + inflation_rate) ** (contract_years_n - 1))
        st.caption(f"Year {contract_years_n} targets: **L=${lav_last:.1f}M, F=${fair_last:.1f}M**")

        st.divider()

        st.subheader("🎯 Optimization Criterion")
        criterion = st.radio(
            "Strike must satisfy:",
            options=[CRITERION_TOTAL_SUM, CRITERION_NPV, CRITERION_WORST_YEAR],
            index=0,
            help=(
                "Total sum: Σ margins ≥ Σ targets over contract life.\n\n"
                "NPV: discounted margins ≥ discounted targets.\n\n"
                "Worst year: every single year must meet its escalated target."
            ),
        )

        if criterion == CRITERION_NPV:
            discount_pct = st.number_input(
                "Discount Rate (% / year)",
                min_value=0.0, max_value=25.0,
                value=DEFAULT_DISCOUNT_RATE * 100,
                step=0.5, format="%.2f",
            )
            discount_rate = discount_pct / 100.0
        else:
            discount_rate = DEFAULT_DISCOUNT_RATE

        st.divider()

        with st.expander("⚙️ Advanced: Price Extrapolation"):
            price_ext_pct = st.number_input(
                "Annual Price Escalation beyond forecast (%)",
                min_value=-5.0, max_value=10.0,
                value=DEFAULT_PRICE_EXTENSION_RATE * 100,
                step=0.25, format="%.2f",
                help="Applied only to years beyond the available forecast data.",
            )
            price_ext_rate = price_ext_pct / 100.0

        st.divider()
        run_forecast = st.button(
            "🔄 Run Multi-Year Forecast",
            type="primary", use_container_width=True,
        )

    # ---- MAIN PANEL - MULTI-YEAR ----
    if 'forecast' not in st.session_state:
        st.session_state.forecast = None
    if 'forecast_min_strike' not in st.session_state:
        st.session_state.forecast_min_strike = None

    if run_forecast:
        with st.spinner(f"Running dispatch for {contract_years_n} years..."):
            try:
                # Load TMY solar (any year works, solar file is TMY-based)
                solar_tmy, _, _, _ = load_all_data(available_years[0])

                # Price loader with cache
                price_cache = {}
                def price_loader(yr):
                    if yr in price_cache:
                        return price_cache[yr]
                    _, hub, lav, fair = load_all_data(yr)
                    price_cache[yr] = (hub, lav, fair)
                    return hub, lav, fair

                progress = st.progress(0, text="Starting dispatch runs...")

                years_list = list(range(contract_start, contract_start + contract_years_n))
                annual_results = []
                degradation_list = []
                extended_years = []
                max_avail = max(available_years)

                for idx, calendar_year in enumerate(years_list, start=1):
                    deg_factor = compute_degradation_factor(idx, first_year_deg, annual_deg)
                    degradation_list.append(deg_factor)
                    degraded = apply_degradation_to_solar(solar_tmy, deg_factor)

                    if calendar_year in available_years:
                        hub, lav, fair = price_loader(calendar_year)
                    else:
                        years_forward = calendar_year - max_avail
                        hub_base, lav_base, fair_base = price_loader(max_avail)
                        hub = escalate_price_array(hub_base, price_ext_rate, years_forward)
                        lav = escalate_price_array(lav_base, price_ext_rate, years_forward)
                        fair = escalate_price_array(fair_base, price_ext_rate, years_forward)
                        extended_years.append(calendar_year)

                    yr_res = run_dispatch_model(
                        solar_df=degraded,
                        hub_prices=hub, lavender_prices=lav, fairway_prices=fair,
                        block_mw=block_mw, start_hour=start_hour, end_hour=end_hour,
                        bess_mwh=bess_mwh, bess_mw=BESS_POWER_MW,
                    )
                    yr_res['calendar_year'] = calendar_year
                    yr_res['year_index'] = idx
                    yr_res['degradation_factor'] = deg_factor
                    yr_res['prices_extended'] = calendar_year in extended_years
                    annual_results.append(yr_res)

                    progress.progress(
                        idx / contract_years_n,
                        text=f"Year {idx}/{contract_years_n} done ({calendar_year})",
                    )

                progress.empty()

                forecast = {
                    'years': years_list,
                    'year_indices': list(range(1, contract_years_n + 1)),
                    'degradation': degradation_list,
                    'annual_results': annual_results,
                    'extended_years': extended_years,
                    'parameters': {
                        'contract_start_year': contract_start,
                        'contract_years': contract_years_n,
                        'block_mw': block_mw,
                        'start_hour': start_hour,
                        'end_hour': end_hour,
                        'bess_mwh': bess_mwh,
                        'bess_mw': BESS_POWER_MW,
                        'first_year_degradation': first_year_deg,
                        'annual_degradation': annual_deg,
                        'price_extension_rate': price_ext_rate,
                    },
                }

                solver = find_min_strike_multiyear(
                    forecast=forecast,
                    lavender_year1_target_m=lav_year1_target,
                    fairway_year1_target_m=fair_year1_target,
                    inflation_rate=inflation_rate,
                    criterion=criterion,
                    discount_rate=discount_rate,
                )
                min_strike_my = solver['min_strike']

                st.session_state.forecast = forecast
                st.session_state.forecast_min_strike = min_strike_my
                st.session_state.forecast_solver = solver
                st.session_state.forecast_inputs = {
                    'lav_target': lav_year1_target,
                    'fair_target': fair_year1_target,
                    'inflation': inflation_rate,
                    'criterion': criterion,
                    'discount_rate': discount_rate,
                    'contract_start': contract_start,
                    'contract_years': contract_years_n,
                    'block_mw': block_mw,
                    'start_hour': start_hour,
                    'end_hour': end_hour,
                    'bess_mwh': bess_mwh,
                    'first_year_deg': first_year_deg,
                    'annual_deg': annual_deg,
                    'price_ext_rate': price_ext_rate,
                }

            except Exception as e:
                st.error(f"Error running forecast: {str(e)}")
                st.exception(e)
                st.stop()

    if st.session_state.forecast is not None:
        forecast = st.session_state.forecast
        min_strike_my = st.session_state.forecast_min_strike
        solver = st.session_state.forecast_solver
        inp = st.session_state.forecast_inputs

        summary_df, totals = multiyear_summary_at_strike(
            forecast=forecast,
            strike_price=min_strike_my,
            lavender_year1_target_m=inp['lav_target'],
            fairway_year1_target_m=inp['fair_target'],
            inflation_rate=inp['inflation'],
            discount_rate=inp['discount_rate'],
        )

        contract_end_y = inp['contract_start'] + inp['contract_years'] - 1
        sum_lav_target = summary_df['lavender_target'].sum() / 1e6
        sum_fair_target = summary_df['fairway_target'].sum() / 1e6

        st.markdown(f"""
        <div class="success-box">
            <h2 style="color: #155724; margin-bottom: 0.5rem;">🎯 Minimum Flat VPPA Strike Price</h2>
            <h1 style="color: {NOFAR_PURPLE}; font-size: 3rem; margin: 0;">${min_strike_my:.2f} /MWh</h1>
            <p style="color: #155724; margin-top: 0.5rem;">
                Flat strike, no escalator, over {inp['contract_years']} years ({inp['contract_start']}–{contract_end_y}).
                Criterion: <strong>{inp['criterion']}</strong>.
                Lifetime targets: L=${sum_lav_target:.1f}M, F=${sum_fair_target:.1f}M (inflated {inp['inflation']*100:.2f}%/yr).
            </p>
        </div>
        """, unsafe_allow_html=True)

        if inp['criterion'] == CRITERION_TOTAL_SUM:
            st.caption(
                f"📊 Binding equation: Σ margins = Σ targets = ${solver['sum_target']/1e6:.2f}M."
            )
        elif inp['criterion'] == CRITERION_NPV:
            st.caption(
                f"📊 NPV(margins) = NPV(targets) = ${solver['discounted_target']/1e6:.2f}M "
                f"at r={inp['discount_rate']*100:.2f}%."
            )
        else:
            binding_y = solver['binding_calendar_year']
            st.caption(f"📊 Binding year: **{binding_y}** (worst year in the contract).")

        if forecast['extended_years']:
            ext_first = forecast['extended_years'][0]
            ext_last = forecast['extended_years'][-1]
            st.markdown(f"""
            <div class="warning-box">
                ⚠️ <strong>Price extrapolation applied:</strong> Years {ext_first}–{ext_last}
                use escalated prices at {inp['price_ext_rate']*100:.2f}% per year, starting from the last available forecast year.
            </div>
            """, unsafe_allow_html=True)

        st.subheader("📊 Lifetime Metrics")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Lifetime Block Volume",
                      f"{summary_df['block_volume'].sum()/1e6:.1f} TWh")
        with c2:
            st.metric("Lifetime Net Margin",
                      f"${totals['total_net_margin']/1e6:.1f} M")
        with c3:
            st.metric("Lifetime Target",
                      f"${totals['total_combined_target']/1e6:.1f} M")
        with c4:
            st.metric("Years Meeting Target",
                      f"{totals['years_meeting_combined_target']}/{totals['total_years']}")
        with c5:
            st.metric("NPV Margin",
                      f"${totals['npv_net_margin']/1e6:.1f} M",
                      help=f"Discount rate: {totals['discount_rate_used']*100:.1f}%")

        st.subheader("📈 Annual Margin vs. Escalated Target")
        st.pyplot(plot_annual_margin_vs_target(summary_df, min_strike_my))

        st.subheader("📊 Cumulative Lifetime Trajectory")
        st.pyplot(plot_cumulative_trajectory(summary_df, min_strike_my, totals))

        st.subheader("💵 Annual Economics Breakdown")
        st.pyplot(plot_annual_economics_stacked(summary_df, min_strike_my))

        st.subheader("🏭 Project-Level Allocation (Pro-rata)")
        st.pyplot(plot_project_allocation_trajectory(summary_df))
        st.caption(
            "Note: Margin is allocated pro-rata based on each project's escalated target share. "
            "Consistent with single-year mode allocation logic."
        )

        st.subheader("☀️ Solar Degradation Impact")
        st.pyplot(plot_solar_degradation(summary_df, forecast['parameters']))

        st.subheader("💹 Price Forecast Trajectory")
        st.pyplot(plot_price_forecast_trajectory(summary_df))

        st.subheader("🥧 Block Coverage Mix by Year")
        st.pyplot(plot_volume_mix_by_year(summary_df))

        st.subheader("📉 Multi-Year Strike Sensitivity")
        sens_df = multiyear_sensitivity(
            forecast=forecast,
            lavender_year1_target_m=inp['lav_target'],
            fairway_year1_target_m=inp['fair_target'],
            inflation_rate=inp['inflation'],
            strike_min=MULTIYEAR_STRIKE_MIN,
            strike_max=MULTIYEAR_STRIKE_MAX,
            strike_step=MULTIYEAR_STRIKE_STEP,
            discount_rate=inp['discount_rate'],
        )
        st.pyplot(plot_multiyear_sensitivity(
            sens_df, min_strike_my, inp['criterion'],
            inp['lav_target'], inp['fair_target'],
            inp['discount_rate'] if inp['criterion'] == CRITERION_NPV else None,
        ))

        st.subheader("📋 Annual Summary Table")
        display_df = summary_df.copy()
        display_df['degradation_factor'] = display_df['degradation_factor'].apply(lambda x: f"{x*100:.2f}%")
        display_df['vppa_revenue'] = display_df['vppa_revenue'].apply(lambda x: f"${x/1e6:.2f}M")
        display_df['merchant_sales_revenue'] = display_df['merchant_sales_revenue'].apply(lambda x: f"${x/1e6:.2f}M")
        display_df['market_cost'] = display_df['market_cost'].apply(lambda x: f"${x/1e6:.2f}M")
        display_df['bess_charge_cost'] = display_df['bess_charge_cost'].apply(lambda x: f"${x/1e6:.2f}M")
        display_df['net_margin'] = display_df['net_margin'].apply(lambda x: f"${x/1e6:.2f}M")
        display_df['combined_target'] = display_df['combined_target'].apply(lambda x: f"${x/1e6:.2f}M")
        display_df['margin_vs_target_pct'] = display_df['margin_vs_target_pct'].apply(lambda x: f"{x:.1f}%")
        display_df['solar_mwh'] = display_df['solar_mwh'].apply(lambda x: f"{x/1000:,.1f} GWh")
        display_df['merchant_mwh'] = display_df['merchant_mwh'].apply(lambda x: f"{x/1000:,.1f} GWh")
        display_df['avg_lavender_basis'] = display_df['avg_lavender_basis'].apply(lambda x: f"${x:.2f}")
        display_df['avg_hub_on_peak'] = display_df['avg_hub_on_peak'].apply(lambda x: f"${x:.2f}")
        display_df['combined_met'] = display_df['combined_met'].apply(lambda x: "✓" if x else "✗")
        display_df['prices_extended'] = display_df['prices_extended'].apply(lambda x: "⚠️" if x else "")

        show_cols = [
            'calendar_year', 'degradation_factor', 'avg_hub_on_peak', 'avg_lavender_basis',
            'solar_mwh', 'merchant_mwh', 'vppa_revenue', 'merchant_sales_revenue',
            'market_cost', 'bess_charge_cost', 'net_margin',
            'combined_target', 'margin_vs_target_pct', 'combined_met', 'prices_extended',
        ]
        show_cols = [c for c in show_cols if c in display_df.columns]
        st.dataframe(display_df[show_cols], hide_index=True, use_container_width=True)

        with st.expander("📋 Sensitivity Data Table"):
            sens_show = sens_df.copy()
            sens_show['strike_price'] = sens_show['strike_price'].apply(lambda x: f"${x:.2f}")
            sens_show['total_margin'] = sens_show['total_margin'].apply(lambda x: f"${x/1e6:.2f}M")
            sens_show['npv_margin'] = sens_show['npv_margin'].apply(lambda x: f"${x/1e6:.2f}M")
            sens_show['total_vppa_revenue'] = sens_show['total_vppa_revenue'].apply(lambda x: f"${x/1e6:.2f}M")
            sens_show['npv_vppa_revenue'] = sens_show['npv_vppa_revenue'].apply(lambda x: f"${x/1e6:.2f}M")
            sens_show['min_annual_margin'] = sens_show['min_annual_margin'].apply(lambda x: f"${x/1e6:.2f}M")
            sens_show['total_target'] = sens_show['total_target'].apply(lambda x: f"${x/1e6:.2f}M")
            sens_show['npv_target'] = sens_show['npv_target'].apply(lambda x: f"${x/1e6:.2f}M")
            st.dataframe(sens_show, hide_index=True, use_container_width=True)

        # Excel export
        st.divider()
        st.subheader("📥 Export Multi-Year Results")
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("""
            Export includes:
            - **Dashboard**: All inputs, the min strike, and lifetime totals
            - **Annual Summary**: Year-by-year economics
            - **Sensitivity**: Lifetime metrics vs. strike price
            - **8760 Hourly Data**: One tab per contract year with full dispatch detail
            """)
        with col2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                dashboard_rows = [
                    ['CONTRACT PARAMETERS', ''],
                    ['Start Year', inp['contract_start']],
                    ['Duration (years)', inp['contract_years']],
                    ['End Year', contract_end_y],
                    ['Block Power (MW)', inp['block_mw']],
                    ['Block Window', f"{inp['start_hour']:02d}:00 - {inp['end_hour']:02d}:00"],
                    ['BESS Capacity (MWh)', inp['bess_mwh']],
                    ['', ''],
                    ['DEGRADATION ASSUMPTIONS', ''],
                    ['First-Year Degradation', f"{inp['first_year_deg']*100:.2f}%"],
                    ['Annual Degradation', f"{inp['annual_deg']*100:.2f}%"],
                    ['Year 1 Capacity Factor', f"{summary_df['degradation_factor'].iloc[0]*100:.2f}%"],
                    [f"Year {inp['contract_years']} Capacity Factor",
                     f"{summary_df['degradation_factor'].iloc[-1]*100:.2f}%"],
                    ['', ''],
                    ['REVENUE TARGETS (Year 1 dollars)', ''],
                    ['Lavender', f"${inp['lav_target']:.2f} M"],
                    ['Fairway', f"${inp['fair_target']:.2f} M"],
                    ['Combined', f"${inp['lav_target'] + inp['fair_target']:.2f} M"],
                    ['Escalation Rate', f"{inp['inflation']*100:.2f}%"],
                    ['Lifetime Target (combined, sum)', f"${totals['total_combined_target']/1e6:.2f} M"],
                    ['Lifetime Target (combined, NPV)', f"${totals['npv_combined_target']/1e6:.2f} M"],
                    ['', ''],
                    ['KEY RESULT', ''],
                    ['Optimization Criterion', inp['criterion']],
                    ['Minimum Flat VPPA Strike', f"${min_strike_my:.2f} /MWh"],
                    ['', ''],
                    ['PRICE EXTRAPOLATION', ''],
                    ['Extended Years', ", ".join(str(y) for y in forecast['extended_years']) or 'None'],
                    ['Price Escalation Rate', f"{inp['price_ext_rate']*100:.2f}%"],
                    ['', ''],
                    ['LIFETIME TOTALS (at min strike)', ''],
                    ['Total VPPA Revenue', f"${totals['total_vppa_revenue']/1e6:.2f} M"],
                    ['Total Merchant Revenue', f"${totals['total_merchant_revenue']/1e6:.2f} M"],
                    ['Total Market Cost', f"${totals['total_market_cost']/1e6:.2f} M"],
                    ['Total BESS Charging Cost', f"${totals['total_bess_cost']/1e6:.2f} M"],
                    ['Total Net Margin', f"${totals['total_net_margin']/1e6:.2f} M"],
                    ['NPV Net Margin', f"${totals['npv_net_margin']/1e6:.2f} M"],
                    ['Discount Rate (NPV)', f"{totals['discount_rate_used']*100:.2f}%"],
                    ['Years Meeting Combined Target', f"{totals['years_meeting_combined_target']}/{totals['total_years']}"],
                ]
                pd.DataFrame(dashboard_rows, columns=['Metric', 'Value']).to_excel(
                    writer, sheet_name='Dashboard', index=False)

                summary_df.to_excel(writer, sheet_name='Annual Summary', index=False)
                sens_df.to_excel(writer, sheet_name='Sensitivity', index=False)

                for yr_res in forecast['annual_results']:
                    cal_year = yr_res['calendar_year']
                    export_df = prepare_export_data(
                        yr_res, min_strike_my, cal_year,
                        inp['lav_target'], inp['fair_target'],
                    )
                    sheet_name = f'8760 {cal_year}'[:31]
                    export_df.to_excel(writer, sheet_name=sheet_name, index=False)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            filename = (
                f"Lavender_Fairway_Forecast_{inp['contract_start']}-{contract_end_y}_"
                f"{inp['block_mw']}MW_{block_hours}hr_{timestamp}.xlsx"
            )
            st.download_button(
                label="📥 Download Excel Report",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", use_container_width=True,
            )

    else:
        st.info("""
        👈 **Configure the contract parameters in the sidebar, then click "Run Multi-Year Forecast"**

        **How this mode works:**
        1. Loads the TMY solar profile (Lavender_PVsyst_P90.CSV) as the year-1 production baseline
        2. Applies year-over-year degradation (configurable, PVsyst defaults shown)
        3. For each contract year, uses the forecast hub / node prices from the CSVs
        4. If the contract extends beyond available forecast years, prices are extrapolated at a configurable rate
        5. Runs full BESS dispatch optimization for every year
        6. Solves analytically for the minimum flat strike price (no escalator) that satisfies the chosen lifetime criterion:
            - **Total sum**: Σ margins ≥ Σ targets
            - **NPV**: discounted margins ≥ discounted targets
            - **Worst year**: every single year must meet its target

        **Default assumptions (editable in sidebar):**
        - Contract: 15 years starting 2028 (Lavender expected COD Dec 31, 2027)
        - First-year degradation: 1.0% (PVsyst default for TOPCon LID/LETID)
        - Annual degradation: 0.4%/year (PVsyst default for TOPCon)
        - Year-1 targets: $20M Lavender + $20M Fairway
        - Target escalation: 2.5%/year (long-term US CPI)
        - Strike: **flat, no escalator** (per Amazon VPPA)
        """)


# =============================================================================
# FOOTER
# =============================================================================
st.divider()
st.caption("""
**Lavender + Fairway VPPA Analyzer** | Built for Blue Sky Utility / Nofar USA  
Model: BESS charges at lowest-price hours, discharges to fill gap during highest-price on-peak hours.  
VPPA CFD: Revenue = Strike + Basis (Node − Hub). Strike is flat across contract life (no escalator).
""")
