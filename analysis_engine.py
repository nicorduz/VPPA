"""
Lavender + Fairway VPPA Analyzer - Analysis Engine
Core dispatch optimization and economic calculations

Key insight: When block parameters change (MW, time window), the BESS dispatch
must be completely recalculated because:
1. Different on-peak hours → different gap hours → different discharge schedule
2. Different gap magnitudes → different energy needed → different charge schedule
3. Different price hours → different arbitrage opportunities
"""

import pandas as pd
import numpy as np
from config import (
    BESS_POWER_MW, BESS_RTE, BESS_AVAILABILITY, BESS_CYCLES_PER_DAY,
    LAVENDER_CAPACITY_AC
)


def run_dispatch_model(solar_df, hub_prices, lavender_prices, fairway_prices,
                       block_mw, start_hour, end_hour, bess_mwh, bess_mw=BESS_POWER_MW):
    """
    Run the complete dispatch optimization model.
    
    Parameters:
    -----------
    solar_df : DataFrame with solar generation (solar_gen_mw column)
    hub_prices : array of 8760 North Hub prices
    lavender_prices : array of 8760 Lavender node prices
    fairway_prices : array of 8760 Fairway node prices
    block_mw : VPPA block power (MW)
    start_hour : Block start hour (0-23)
    end_hour : Block end hour (1-24)
    bess_mwh : BESS energy capacity (MWh)
    bess_mw : BESS power capacity (MW)
    
    Returns:
    --------
    dict with 'model' (DataFrame) and summary statistics
    """
    
    # Build the 8760 model DataFrame
    model = solar_df.copy()
    
    # Add price data
    model['north_hub_price'] = hub_prices
    model['lavender_node_price'] = lavender_prices
    model['fairway_node_price'] = fairway_prices
    
    # Calculate basis
    model['lavender_basis'] = model['lavender_node_price'] - model['north_hub_price']
    model['fairway_basis'] = model['fairway_node_price'] - model['north_hub_price']
    
    # Mark on-peak hours based on configurable window
    model['is_on_peak'] = (model['hour_of_day'] >= start_hour) & (model['hour_of_day'] < end_hour)
    
    # Block obligation (only during on-peak)
    model['block_obligation_mw'] = model['is_on_peak'].astype(float) * block_mw
    
    # Solar allocation:
    # 1) first covers the VPPA block
    # 2) any excess is sold merchant at Lavender node price
    model['solar_to_block_mw'] = np.minimum(
        model['solar_gen_mw'],
        model['block_obligation_mw']
    )

    # Keep old column name for compatibility with app.py / plots
    model['solar_delivered_mw'] = model['solar_to_block_mw']

    model['solar_excess_mw'] = np.maximum(
        model['solar_gen_mw'] - model['solar_to_block_mw'],
        0.0
    )

    # Remaining block after solar
    model['gap_before_bess_mw'] = np.maximum(
        model['block_obligation_mw'] - model['solar_to_block_mw'],
        0.0
    )
    
    # Initialize BESS columns
    model['bess_discharge_mw'] = 0.0
    model['bess_charge_mw'] = 0.0
    
    # Effective BESS capacity per day
    effective_capacity = bess_mwh * BESS_AVAILABILITY * BESS_CYCLES_PER_DAY
    
    # Run daily BESS dispatch optimization
    for day in range(1, 366):
        day_mask = model['day_of_year'] == day
        day_data = model[day_mask].copy()
        
        if len(day_data) == 0:
            continue
        
        # Get indices for this day
        day_indices = model.index[day_mask].tolist()
        
        # =====================================================================
        # PASS 1: Determine discharge schedule (highest-priced gap hours)
        # =====================================================================
        
        # Find on-peak hours with gap, sorted by price (highest first)
        on_peak_gap_hours = day_data[
            (day_data['is_on_peak']) & (day_data['gap_before_bess_mw'] > 0)
        ].copy()
        
        if len(on_peak_gap_hours) > 0:
            # Sort by Lavender node price descending (discharge when prices highest)
            on_peak_gap_hours = on_peak_gap_hours.sort_values('lavender_node_price', ascending=False)
            
            energy_remaining = effective_capacity
            discharge_hours = []
            
            for idx in on_peak_gap_hours.index:
                if energy_remaining <= 0:
                    break
                
                gap = on_peak_gap_hours.loc[idx, 'gap_before_bess_mw']
                
                # Discharge amount = min(power limit, gap, energy remaining)
                discharge = min(bess_mw, gap, energy_remaining)
                
                if discharge > 0:
                    model.loc[idx, 'bess_discharge_mw'] = discharge
                    discharge_hours.append(idx)
                    energy_remaining -= discharge
        
        # =====================================================================
        # PASS 2: Determine charge schedule (lowest-priced hours of entire day)
        # =====================================================================
        
        total_discharge = model.loc[day_indices, 'bess_discharge_mw'].sum()
        
        if total_discharge > 0:
            # Need to charge enough to cover discharge plus losses
            charge_needed = total_discharge / BESS_RTE
            
            # Find cheapest hours across the ENTIRE day (not just on-peak)
            # Exclude hours when we're discharging
            discharge_indices = set(model.loc[day_indices][model.loc[day_indices, 'bess_discharge_mw'] > 0].index)
            
            chargeable_hours = day_data[~day_data.index.isin(discharge_indices)].copy()
            
            if len(chargeable_hours) > 0:
                # Sort by Fairway node price ascending (charge when cheapest)
                chargeable_hours = chargeable_hours.sort_values('fairway_node_price', ascending=True)
                
                charge_accumulated = 0.0
                
                for idx in chargeable_hours.index:
                    if charge_accumulated >= charge_needed:
                        break
                    
                    # Charge amount = min(power limit, what we still need)
                    charge = min(bess_mw, charge_needed - charge_accumulated)
                    
                    if charge > 0:
                        model.loc[idx, 'bess_charge_mw'] = charge
                        charge_accumulated += charge
    
    # =========================================================================
    # Calculate final gap and costs
    # =========================================================================
    
    # BESS allocation:
    # 1) first covers the remaining VPPA block
    # 2) any excess is sold merchant at Fairway node price
    model['bess_to_block_mw'] = np.minimum(
        model['bess_discharge_mw'],
        model['gap_before_bess_mw']
    )

    model['bess_excess_mw'] = np.maximum(
        model['bess_discharge_mw'] - model['bess_to_block_mw'],
        0.0
    )

    # Final uncovered block after BESS
    model['gap_mw'] = np.maximum(
        model['block_obligation_mw'] - model['solar_to_block_mw'] - model['bess_to_block_mw'],
        0.0
    )

    # Costs
    model['bess_charge_cost'] = model['bess_charge_mw'] * model['fairway_node_price']
    model['market_purchase_cost'] = model['gap_mw'] * model['lavender_node_price']

    # Merchant revenues from excess energy
    model['solar_excess_revenue'] = model['solar_excess_mw'] * model['lavender_node_price']
    model['bess_excess_revenue'] = model['bess_excess_mw'] * model['fairway_node_price']
    model['merchant_sales_revenue'] = model['solar_excess_revenue'] + model['bess_excess_revenue']
    
    # =========================================================================
    # Calculate summary statistics
    # =========================================================================
    
    # Volume calculations
    block_hours = end_hour - start_hour
    total_block_volume = block_mw * block_hours * 365
    
    on_peak_data = model[model['is_on_peak']]
    
    solar_contribution = on_peak_data['solar_to_block_mw'].sum()
    bess_contribution = on_peak_data['bess_to_block_mw'].sum()
    merchant_volume = on_peak_data['gap_mw'].sum()

    solar_excess_volume = model['solar_excess_mw'].sum()
    bess_excess_volume = model['bess_excess_mw'].sum()

    # Cost calculations
    total_market_cost = model['market_purchase_cost'].sum()
    total_bess_charge_cost = model['bess_charge_cost'].sum()
    total_merchant_sales_revenue = model['merchant_sales_revenue'].sum()
    total_costs = total_market_cost + total_bess_charge_cost

    # BESS economics proxy
    bess_discharge_revenue_equiv = (
        (model['bess_to_block_mw'] * model['lavender_node_price']).sum() +
        (model['bess_excess_mw'] * model['fairway_node_price']).sum()
    )
    bess_gross_spread = bess_discharge_revenue_equiv - total_bess_charge_cost
    
    # Average prices
    avg_hub_on_peak = on_peak_data['north_hub_price'].mean()
    avg_lavender_on_peak = on_peak_data['lavender_node_price'].mean()
    avg_lavender_basis = on_peak_data['lavender_basis'].mean()
    
    # Charging analysis
    charge_hours_mask = model['bess_charge_mw'] > 0
    if charge_hours_mask.sum() > 0:
        avg_charge_price = (model.loc[charge_hours_mask, 'bess_charge_mw'] * 
                           model.loc[charge_hours_mask, 'fairway_node_price']).sum() / \
                          model.loc[charge_hours_mask, 'bess_charge_mw'].sum()
    else:
        avg_charge_price = 0
    
    discharge_hours_mask = model['bess_discharge_mw'] > 0
    if discharge_hours_mask.sum() > 0:
        total_discharge_value = (
            (model['bess_to_block_mw'] * model['lavender_node_price']).sum() +
            (model['bess_excess_mw'] * model['fairway_node_price']).sum()
        )
        avg_discharge_price = total_discharge_value / model['bess_discharge_mw'].sum()
    else:
        avg_discharge_price = 0
    
    bess_spread = avg_discharge_price - avg_charge_price / BESS_RTE if avg_charge_price > 0 else 0
    
    # Off-peak vs on-peak charging analysis
    total_charge = model['bess_charge_mw'].sum()
    off_peak_charge = model[~model['is_on_peak']]['bess_charge_mw'].sum()
    off_peak_charge_pct = (off_peak_charge / total_charge * 100) if total_charge > 0 else 0
    
    results = {
        'model': model,
        
        # Volume metrics
        'block_volume': total_block_volume,
        'solar_mwh': solar_contribution,
        'bess_mwh': bess_contribution,
        'merchant_mwh': merchant_volume,
        'solar_pct': solar_contribution / total_block_volume * 100,
        'bess_pct': bess_contribution / total_block_volume * 100,
        'merchant_pct': merchant_volume / total_block_volume * 100,
        
        # Cost metrics
        'market_cost': total_market_cost,
        'bess_charge_cost': total_bess_charge_cost,
        'total_costs': total_costs,
        
        # BESS metrics
        'bess_gross_spread': bess_gross_spread,
        'avg_charge_price': avg_charge_price,
        'avg_discharge_price': avg_discharge_price,
        'bess_spread_per_mwh': bess_spread,
        'off_peak_charge_pct': off_peak_charge_pct,
        
        # Price metrics
        'avg_hub_on_peak': avg_hub_on_peak,
        'avg_lavender_on_peak': avg_lavender_on_peak,
        'avg_lavender_basis': avg_lavender_basis,
        
        # Parameters used
        'block_mw': block_mw,
        'start_hour': start_hour,
        'end_hour': end_hour,
        'block_hours': block_hours,
        'bess_mwh': bess_mwh,
        'bess_mw': bess_mw,

        'solar_excess_mwh': solar_excess_volume,
        'bess_excess_mwh': bess_excess_volume,
        'solar_excess_revenue': model['solar_excess_revenue'].sum(),
        'bess_excess_revenue': model['bess_excess_revenue'].sum(),
        'merchant_sales_revenue': total_merchant_sales_revenue,
    }
    
    return results


def calculate_min_strike(results, required_margin):
    """
    Minimum VPPA strike needed to achieve required net margin.

    Net Margin = VPPA Revenue + Merchant Sales Revenue - Total Costs

    VPPA Revenue = Block Volume × (Strike + Avg Basis)

    Therefore:
    Strike = (Required Margin + Total Costs - Merchant Sales Revenue) / Block Volume - Avg Basis
    """
    block_volume = results['block_volume']
    total_costs = results['total_costs']
    avg_basis = results['avg_lavender_basis']
    merchant_sales_revenue = results.get('merchant_sales_revenue', 0.0)

    min_strike = (
        (required_margin + total_costs - merchant_sales_revenue) / block_volume
        - avg_basis
    )

    return min_strike


def calculate_margin_at_strike(results, strike_price):
    """
    Net margin at a given strike price.

    Margin = VPPA Revenue + Merchant Sales Revenue - Total Costs
    """
    block_volume = results['block_volume']
    total_costs = results['total_costs']
    avg_basis = results['avg_lavender_basis']
    merchant_sales_revenue = results.get('merchant_sales_revenue', 0.0)

    vppa_revenue = block_volume * (strike_price + avg_basis)
    margin = vppa_revenue + merchant_sales_revenue - total_costs

    return margin


def calculate_vppa_revenue_at_strike(results, strike_price):
    """
    Calculate total VPPA revenue at a given strike price.
    """
    block_volume = results['block_volume']
    avg_basis = results['avg_lavender_basis']
    
    return block_volume * (strike_price + avg_basis)


def run_sensitivity_analysis(results, strike_min=40, strike_max=90, strike_step=2.5):
    """
    Run strike price sensitivity analysis.
    
    Returns DataFrame with margin at each strike price.
    """
    
    strikes = np.arange(strike_min, strike_max + strike_step, strike_step)
    
    data = []
    for strike in strikes:
        margin = calculate_margin_at_strike(results, strike)
        revenue = calculate_vppa_revenue_at_strike(results, strike)
        
        data.append({
            'strike_price': strike,
            'vppa_revenue': revenue,
            'total_costs': results['total_costs'],
            'net_margin': margin,
            'margin_per_mwh': margin / results['block_volume']
        })
    
    return pd.DataFrame(data)


def allocate_margin_to_projects(total_margin, lavender_target, fairway_target):
    """
    Allocate total margin between Lavender and Fairway projects.
    
    Uses a pro-rata allocation based on targets.
    
    Returns:
    --------
    dict with allocation results
    """
    
    total_target = lavender_target + fairway_target
    
    if total_target <= 0:
        return {
            'lavender_margin': 0,
            'fairway_margin': 0,
            'lavender_met': False,
            'fairway_met': False
        }
    
    lavender_share = lavender_target / total_target
    fairway_share = fairway_target / total_target
    
    lavender_margin = total_margin * lavender_share
    fairway_margin = total_margin * fairway_share
    
    return {
        'lavender_margin': lavender_margin,
        'fairway_margin': fairway_margin,
        'lavender_met': lavender_margin >= lavender_target,
        'fairway_met': fairway_margin >= fairway_target
    }


def add_economics_to_model(model, strike_price, start_hour, end_hour):
    """
    Add VPPA revenue and net margin columns to the 8760 model at a specific strike price.
    """
    model = model.copy()

    # VPPA CFD revenue on contracted block only
    model['vppa_revenue_per_mwh'] = np.where(
        model['is_on_peak'],
        strike_price + model['lavender_basis'],
        0.0
    )

    model['vppa_revenue'] = model['block_obligation_mw'] * model['vppa_revenue_per_mwh']

    # Merchant revenues from excess generation
    model['solar_excess_revenue'] = model['solar_excess_mw'] * model['lavender_node_price']
    model['bess_excess_revenue'] = model['bess_excess_mw'] * model['fairway_node_price']
    model['merchant_sales_revenue'] = model['solar_excess_revenue'] + model['bess_excess_revenue']

    # Hourly net margin
    model['net_margin'] = (
        model['vppa_revenue']
        + model['merchant_sales_revenue']
        - model['market_purchase_cost']
        - model['bess_charge_cost']
    )

    return model


def prepare_export_data(results, strike_price, year, lavender_target, fairway_target):
    """
    Prepare data for Excel export with all relevant columns and economics.
    """
    
    model = results['model'].copy()
    
    # Add economics at the found strike price
    model = add_economics_to_model(
        model, 
        strike_price, 
        results['start_hour'], 
        results['end_hour']
    )
    
    # Add metadata columns
    model['year'] = year
    model['vppa_strike_price'] = strike_price
    model['block_power_mw'] = results['block_mw']
    model['block_start_hour'] = results['start_hour']
    model['block_end_hour'] = results['end_hour']
    
    # Reorder columns for clarity
    column_order = [
        'year', 'hour_of_year', 'day_of_year', 'month', 'hour_of_day', 'is_on_peak',
        'block_power_mw', 'block_start_hour', 'block_end_hour', 'vppa_strike_price',
        'solar_gen_mw', 'solar_delivered_mw', 'solar_to_block_mw', 'solar_excess_mw',
        'block_obligation_mw',
        'bess_discharge_mw', 'bess_to_block_mw', 'bess_excess_mw', 'bess_charge_mw', 'gap_mw',
        'north_hub_price', 'lavender_node_price', 'fairway_node_price',
        'lavender_basis', 'fairway_basis',
        'vppa_revenue_per_mwh', 'vppa_revenue',
        'solar_excess_revenue', 'bess_excess_revenue', 'merchant_sales_revenue',
        'market_purchase_cost', 'bess_charge_cost', 'net_margin'
    ]
    
    # Only include columns that exist
    columns_to_use = [col for col in column_order if col in model.columns]
    model = model[columns_to_use]
    
    return model


def create_summary_df(results, min_strike, year, lavender_target, fairway_target):
    """
    Create a summary DataFrame for the Dashboard sheet in Excel.
    """
    
    total_margin = calculate_margin_at_strike(results, min_strike)
    allocation = allocate_margin_to_projects(total_margin, lavender_target * 1e6, fairway_target * 1e6)
    
    summary_data = [
        ['ANALYSIS PARAMETERS', ''],
        ['Year', year],
        ['Block Power (MW)', results['block_mw']],
        ['Block Window', f"{results['start_hour']}:00 - {results['end_hour']}:00"],
        ['Block Duration (hours/day)', results['block_hours']],
        ['BESS Capacity (MWh)', results['bess_mwh']],
        ['BESS Power (MW)', results['bess_mw']],
        ['', ''],
        ['REVENUE TARGETS', ''],
        ['Lavender Target', f"${lavender_target:.1f} M/year"],
        ['Fairway Target', f"${fairway_target:.1f} M/year"],
        ['Combined Target', f"${lavender_target + fairway_target:.1f} M/year"],
        ['', ''],
        ['KEY RESULT', ''],
        ['Minimum VPPA Strike Price', f"${min_strike:.2f} /MWh"],
        ['', ''],
        ['VOLUME BREAKDOWN', ''],
        ['Total Block Volume', f"{results['block_volume']:,.0f} MWh"],
        ['Solar Contribution', f"{results['solar_mwh']:,.0f} MWh ({results['solar_pct']:.1f}%)"],
        ['BESS Contribution', f"{results['bess_mwh']:,.0f} MWh ({results['bess_pct']:.1f}%)"],
        ['Merchant Purchase', f"{results['merchant_mwh']:,.0f} MWh ({results['merchant_pct']:.1f}%)"],
        ['', ''],
        ['ECONOMICS (at min strike)', ''],
        ['VPPA Revenue', f"${calculate_vppa_revenue_at_strike(results, min_strike)/1e6:.2f} M"],
        ['Market Purchase Cost', f"${results['market_cost']/1e6:.2f} M"],
        ['BESS Charging Cost', f"${results['bess_charge_cost']/1e6:.2f} M"],
        ['Total Costs', f"${results['total_costs']/1e6:.2f} M"],
        ['Net Margin', f"${total_margin/1e6:.2f} M"],
        ['', ''],
        ['MARGIN ALLOCATION', ''],
        ['Lavender Margin', f"${allocation['lavender_margin']/1e6:.2f} M"],
        ['Fairway Margin', f"${allocation['fairway_margin']/1e6:.2f} M"],
        ['', ''],
        ['BESS PERFORMANCE', ''],
        ['Avg Charge Price (Fairway)', f"${results['avg_charge_price']:.2f} /MWh"],
        ['Avg Discharge Price (Lavender)', f"${results['avg_discharge_price']:.2f} /MWh"],
        ['BESS Spread (net of RTE)', f"${results['bess_spread_per_mwh']:.2f} /MWh"],
        ['Off-Peak Charging', f"{results['off_peak_charge_pct']:.1f}%"],
        ['BESS Gross Spread', f"${results['bess_gross_spread']/1e6:.2f} M"],
        ['', ''],
        ['PRICE METRICS', ''],
        ['Avg Hub On-Peak Price', f"${results['avg_hub_on_peak']:.2f} /MWh"],
        ['Avg Lavender Node Price', f"${results['avg_lavender_on_peak']:.2f} /MWh"],
        ['Avg Lavender Basis', f"${results['avg_lavender_basis']:.2f} /MWh"],
    ]
    
    return pd.DataFrame(summary_data, columns=['Metric', 'Value'])


# =============================================================================
# MULTI-YEAR FORECAST ENGINE
# =============================================================================
#
# Approach:
# 1. Load a single TMY solar profile (Lavender_PVsyst_P90.CSV) = year-1 production.
# 2. For each contract year, apply a degradation factor to the TMY solar profile.
# 3. For each contract year, load that year's forecast prices (Hub, Lavender, Fairway).
#    If the contract extends beyond available forecast years, extend the last
#    available year forward using a configurable price extension rate.
# 4. Run the dispatch model once per year.
# 5. Given a trial flat strike price, compute each year's margin.
# 6. Find the minimum flat strike that satisfies one of three criteria:
#      (a) TOTAL_SUM   - Sum(margin) >= Sum(target) over the contract life
#      (b) NPV         - NPV(margin) >= NPV(target) at a configurable discount rate
#      (c) WORST_YEAR  - Every individual year must meet its escalated target
#
# Because VPPA revenue is linear in strike (Revenue = BlockVol * (Strike + AvgBasis)),
# every criterion reduces to a closed-form expression. No numerical search is needed.
# =============================================================================


def compute_degradation_factor(year_index, first_year_degradation, annual_degradation):
    """
    Degradation factor for a given contract year (1-indexed).

    Model: factor = (1 - first_year_deg) * (1 - annual_deg)^(year_index - 1)

    Year 1 applies first-year LID/LETID only.
    Year 2 onwards compounds annual degradation on top of that.
    """
    if year_index < 1:
        raise ValueError("year_index must be >= 1")
    return (1.0 - first_year_degradation) * ((1.0 - annual_degradation) ** (year_index - 1))


def apply_degradation_to_solar(solar_df, degradation_factor):
    """
    Return a copy of the solar DataFrame with solar_gen_mw scaled by the degradation factor.
    """
    degraded = solar_df.copy()
    degraded['solar_gen_mw'] = degraded['solar_gen_mw'] * degradation_factor
    return degraded


def escalate_price_array(price_array, escalation_rate, years_forward):
    """
    Escalate a price array (8760 length) by an annual rate compounded over years_forward years.
    Used when the forecast does not cover the full contract horizon.
    """
    factor = (1.0 + escalation_rate) ** years_forward
    return price_array * factor


def run_multiyear_forecast(
    solar_tmy_df,
    price_loader,
    contract_start_year,
    contract_years,
    block_mw,
    start_hour,
    end_hour,
    bess_mwh,
    bess_mw,
    first_year_degradation,
    annual_degradation,
    price_extension_rate,
    available_years,
):
    """
    Run the dispatch model for every year of the contract.

    Parameters
    ----------
    solar_tmy_df : DataFrame
        Single TMY solar profile (pre-degradation). Must have 'solar_gen_mw',
        'hour_of_day', 'day_of_year', 'month' columns.
    price_loader : callable(year) -> (hub, lavender, fairway)
        Function that returns the three 8760 price arrays for a given year.
    contract_start_year : int
        First year of the contract (e.g. 2028).
    contract_years : int
        Number of contract years (e.g. 15).
    block_mw, start_hour, end_hour, bess_mwh, bess_mw :
        Same as single-year dispatch model.
    first_year_degradation, annual_degradation : float
        Degradation model inputs (see compute_degradation_factor).
    price_extension_rate : float
        If a contract year falls beyond the last available forecast year,
        escalate the last available year's prices at this rate per year.
    available_years : list[int]
        Forecast years available from the data files.

    Returns
    -------
    dict with:
        'years'            : list of contract years
        'year_indices'     : list of 1-indexed year positions
        'degradation'      : list of degradation factors per year
        'annual_results'   : list of dispatch results dicts (one per year)
        'extended_years'   : list of years where prices were extrapolated
        'parameters'       : dict of inputs used
    """
    years = list(range(contract_start_year, contract_start_year + contract_years))
    max_available = max(available_years)

    annual_results = []
    degradation_list = []
    extended_years = []

    for idx, calendar_year in enumerate(years, start=1):
        # Degradation
        deg_factor = compute_degradation_factor(idx, first_year_degradation, annual_degradation)
        degradation_list.append(deg_factor)
        degraded_solar = apply_degradation_to_solar(solar_tmy_df, deg_factor)

        # Prices - use forecast if available, otherwise extend last available year
        if calendar_year in available_years:
            hub, lav, fair = price_loader(calendar_year)
        else:
            years_forward = calendar_year - max_available
            hub_base, lav_base, fair_base = price_loader(max_available)
            hub = escalate_price_array(hub_base, price_extension_rate, years_forward)
            lav = escalate_price_array(lav_base, price_extension_rate, years_forward)
            fair = escalate_price_array(fair_base, price_extension_rate, years_forward)
            extended_years.append(calendar_year)

        # Dispatch
        year_result = run_dispatch_model(
            solar_df=degraded_solar,
            hub_prices=hub,
            lavender_prices=lav,
            fairway_prices=fair,
            block_mw=block_mw,
            start_hour=start_hour,
            end_hour=end_hour,
            bess_mwh=bess_mwh,
            bess_mw=bess_mw,
        )
        year_result['calendar_year'] = calendar_year
        year_result['year_index'] = idx
        year_result['degradation_factor'] = deg_factor
        year_result['prices_extended'] = calendar_year in extended_years

        annual_results.append(year_result)

    return {
        'years': years,
        'year_indices': list(range(1, contract_years + 1)),
        'degradation': degradation_list,
        'annual_results': annual_results,
        'extended_years': extended_years,
        'parameters': {
            'contract_start_year': contract_start_year,
            'contract_years': contract_years,
            'block_mw': block_mw,
            'start_hour': start_hour,
            'end_hour': end_hour,
            'bess_mwh': bess_mwh,
            'bess_mw': bess_mw,
            'first_year_degradation': first_year_degradation,
            'annual_degradation': annual_degradation,
            'price_extension_rate': price_extension_rate,
        },
    }


def escalated_targets(year1_target_m, inflation_rate, contract_years):
    """
    Return the per-year escalated revenue target in dollars (not millions).

    target_y = year1_target * (1 + inflation)^(y-1)
    """
    return np.array([
        year1_target_m * 1e6 * ((1.0 + inflation_rate) ** (y - 1))
        for y in range(1, contract_years + 1)
    ])


def annual_margin_at_strike(year_result, strike_price):
    """
    Net margin for a single year at a given flat strike price.
    """
    return calculate_margin_at_strike(year_result, strike_price)


def annual_vppa_revenue_at_strike(year_result, strike_price):
    return calculate_vppa_revenue_at_strike(year_result, strike_price)


def lifetime_margin_series(forecast, strike_price):
    """
    Array of annual margins over the full contract at a given flat strike.
    """
    return np.array([
        annual_margin_at_strike(yr, strike_price)
        for yr in forecast['annual_results']
    ])


def discount_factors(discount_rate, contract_years):
    """
    Discount factors for NPV. Year 1 is discounted by 1/(1+r) (end-of-year convention).
    """
    return np.array([
        1.0 / ((1.0 + discount_rate) ** y)
        for y in range(1, contract_years + 1)
    ])


def find_min_strike_multiyear(
    forecast,
    lavender_year1_target_m,
    fairway_year1_target_m,
    inflation_rate,
    criterion,
    discount_rate=0.08,
):
    """
    Find the minimum flat VPPA strike price that satisfies the chosen lifetime criterion.

    VPPA revenue is linear in strike, so each criterion reduces to a closed-form:

        Margin_y(S) = Block_y * S + K_y
        where K_y = Block_y * AvgBasis_y + MerchantRev_y - TotalCosts_y

    (a) TOTAL_SUM:  Sum(Margin_y) >= Sum(Target_y)
                    S >= (Sum(Target_y) - Sum(K_y)) / Sum(Block_y)

    (b) NPV:        Sum(DF_y * Margin_y) >= Sum(DF_y * Target_y)
                    S >= (Sum(DF_y * Target_y) - Sum(DF_y * K_y)) / Sum(DF_y * Block_y)

    (c) WORST_YEAR: Margin_y >= Target_y for every y
                    S_y = (Target_y - K_y) / Block_y
                    S   = max(S_y)

    Returns
    -------
    dict with 'min_strike', 'criterion', and intermediate diagnostic values.
    """
    from config import CRITERION_TOTAL_SUM, CRITERION_NPV, CRITERION_WORST_YEAR

    annual = forecast['annual_results']
    n_years = len(annual)

    block_volumes = np.array([yr['block_volume'] for yr in annual])
    avg_basis = np.array([yr['avg_lavender_basis'] for yr in annual])
    merchant_rev = np.array([yr['merchant_sales_revenue'] for yr in annual])
    total_costs = np.array([yr['total_costs'] for yr in annual])

    # K_y = Block_y * AvgBasis_y + MerchantRev_y - TotalCosts_y
    k_array = block_volumes * avg_basis + merchant_rev - total_costs

    # Per-year target (combined = Lavender + Fairway, each escalated from year 1)
    lav_targets = escalated_targets(lavender_year1_target_m, inflation_rate, n_years)
    fair_targets = escalated_targets(fairway_year1_target_m, inflation_rate, n_years)
    combined_targets = lav_targets + fair_targets

    result = {
        'criterion': criterion,
        'block_volumes': block_volumes,
        'k_array': k_array,
        'lavender_targets': lav_targets,
        'fairway_targets': fair_targets,
        'combined_targets': combined_targets,
    }

    if criterion == CRITERION_TOTAL_SUM:
        sum_block = block_volumes.sum()
        sum_k = k_array.sum()
        sum_target = combined_targets.sum()
        min_strike = (sum_target - sum_k) / sum_block
        result['min_strike'] = min_strike
        result['sum_block'] = sum_block
        result['sum_target'] = sum_target
        result['sum_k'] = sum_k

    elif criterion == CRITERION_NPV:
        df = discount_factors(discount_rate, n_years)
        disc_block = (df * block_volumes).sum()
        disc_k = (df * k_array).sum()
        disc_target = (df * combined_targets).sum()
        min_strike = (disc_target - disc_k) / disc_block
        result['min_strike'] = min_strike
        result['discount_rate'] = discount_rate
        result['discount_factors'] = df
        result['discounted_target'] = disc_target
        result['discounted_block'] = disc_block
        result['discounted_k'] = disc_k

    elif criterion == CRITERION_WORST_YEAR:
        per_year_strikes = (combined_targets - k_array) / block_volumes
        min_strike = per_year_strikes.max()
        binding_idx = int(np.argmax(per_year_strikes))
        result['min_strike'] = min_strike
        result['per_year_min_strikes'] = per_year_strikes
        result['binding_year_index'] = binding_idx
        result['binding_calendar_year'] = forecast['years'][binding_idx]

    else:
        raise ValueError(f"Unknown criterion: {criterion}")

    return result


def multiyear_summary_at_strike(
    forecast,
    strike_price,
    lavender_year1_target_m,
    fairway_year1_target_m,
    inflation_rate,
    discount_rate=0.08,
):
    """
    Build a per-year summary DataFrame at a given flat strike price.

    Lavender/Fairway margin allocation is pro-rata based on the escalated target split
    in each year (consistent with allocate_margin_to_projects in single-year mode).
    """
    annual = forecast['annual_results']
    n_years = len(annual)

    lav_targets = escalated_targets(lavender_year1_target_m, inflation_rate, n_years)
    fair_targets = escalated_targets(fairway_year1_target_m, inflation_rate, n_years)
    combined_targets = lav_targets + fair_targets

    rows = []
    for yr, lav_t, fair_t, combined_t in zip(annual, lav_targets, fair_targets, combined_targets):
        vppa_rev = annual_vppa_revenue_at_strike(yr, strike_price)
        margin = annual_margin_at_strike(yr, strike_price)

        if combined_t > 0:
            lav_share = lav_t / combined_t
            fair_share = fair_t / combined_t
        else:
            lav_share = fair_share = 0.5

        lav_margin = margin * lav_share
        fair_margin = margin * fair_share

        rows.append({
            'calendar_year': yr['calendar_year'],
            'year_index': yr['year_index'],
            'degradation_factor': yr['degradation_factor'],
            'prices_extended': yr['prices_extended'],
            'solar_mwh': yr['solar_mwh'],
            'bess_mwh_to_block': yr['block_volume'] * yr['bess_pct'] / 100.0,
            'merchant_mwh': yr['merchant_mwh'],
            'solar_excess_mwh': yr.get('solar_excess_mwh', 0.0),
            'bess_excess_mwh': yr.get('bess_excess_mwh', 0.0),
            'solar_pct': yr['solar_pct'],
            'bess_pct': yr['bess_pct'],
            'merchant_pct': yr['merchant_pct'],
            'avg_hub_on_peak': yr['avg_hub_on_peak'],
            'avg_lavender_on_peak': yr['avg_lavender_on_peak'],
            'avg_lavender_basis': yr['avg_lavender_basis'],
            'block_volume': yr['block_volume'],
            'vppa_revenue': vppa_rev,
            'merchant_sales_revenue': yr['merchant_sales_revenue'],
            'market_cost': yr['market_cost'],
            'bess_charge_cost': yr['bess_charge_cost'],
            'total_costs': yr['total_costs'],
            'net_margin': margin,
            'lavender_target': lav_t,
            'fairway_target': fair_t,
            'combined_target': combined_t,
            'lavender_margin_alloc': lav_margin,
            'fairway_margin_alloc': fair_margin,
            'lavender_met': lav_margin >= lav_t,
            'fairway_met': fair_margin >= fair_t,
            'combined_met': margin >= combined_t,
            'margin_vs_target_pct': (margin / combined_t * 100) if combined_t > 0 else 0,
        })

    df = pd.DataFrame(rows)

    # Lifetime totals and NPV
    totals = {
        'total_vppa_revenue': df['vppa_revenue'].sum(),
        'total_merchant_revenue': df['merchant_sales_revenue'].sum(),
        'total_market_cost': df['market_cost'].sum(),
        'total_bess_cost': df['bess_charge_cost'].sum(),
        'total_net_margin': df['net_margin'].sum(),
        'total_combined_target': df['combined_target'].sum(),
        'total_lavender_target': df['lavender_target'].sum(),
        'total_fairway_target': df['fairway_target'].sum(),
        'years_meeting_combined_target': int(df['combined_met'].sum()),
        'total_years': n_years,
    }

    df_disc = discount_factors(discount_rate, n_years)
    totals['npv_net_margin'] = float((df['net_margin'].values * df_disc).sum())
    totals['npv_combined_target'] = float((df['combined_target'].values * df_disc).sum())
    totals['npv_lavender_target'] = float((df['lavender_target'].values * df_disc).sum())
    totals['npv_fairway_target'] = float((df['fairway_target'].values * df_disc).sum())
    totals['npv_vppa_revenue'] = float((df['vppa_revenue'].values * df_disc).sum())
    totals['npv_merchant_revenue'] = float((df['merchant_sales_revenue'].values * df_disc).sum())
    totals['npv_total_costs'] = float((df['total_costs'].values * df_disc).sum())
    totals['discount_rate_used'] = discount_rate

    return df, totals


def multiyear_sensitivity(
    forecast,
    lavender_year1_target_m,
    fairway_year1_target_m,
    inflation_rate,
    strike_min=30.0,
    strike_max=100.0,
    strike_step=2.5,
    discount_rate=0.08,
):
    """
    Sweep the strike price and return aggregate lifetime metrics at each strike.
    """
    strikes = np.arange(strike_min, strike_max + strike_step, strike_step)
    rows = []

    annual = forecast['annual_results']
    n_years = len(annual)
    block_volumes = np.array([yr['block_volume'] for yr in annual])
    avg_basis = np.array([yr['avg_lavender_basis'] for yr in annual])
    merchant_rev = np.array([yr['merchant_sales_revenue'] for yr in annual])
    total_costs = np.array([yr['total_costs'] for yr in annual])

    lav_targets = escalated_targets(lavender_year1_target_m, inflation_rate, n_years)
    fair_targets = escalated_targets(fairway_year1_target_m, inflation_rate, n_years)
    combined_targets = lav_targets + fair_targets
    df_disc = discount_factors(discount_rate, n_years)

    for s in strikes:
        vppa_rev_y = block_volumes * (s + avg_basis)
        margin_y = vppa_rev_y + merchant_rev - total_costs

        rows.append({
            'strike_price': s,
            'total_margin': margin_y.sum(),
            'total_vppa_revenue': vppa_rev_y.sum(),
            'npv_margin': float((margin_y * df_disc).sum()),
            'npv_vppa_revenue': float((vppa_rev_y * df_disc).sum()),
            'years_meeting_target': int(np.sum(margin_y >= combined_targets)),
            'total_target': combined_targets.sum(),
            'npv_target': float((combined_targets * df_disc).sum()),
            'min_annual_margin': margin_y.min(),
            'worst_year_idx': int(np.argmin(margin_y - combined_targets)),
        })

    return pd.DataFrame(rows)
