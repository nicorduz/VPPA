"""
Lavender + Fairway VPPA Analyzer - Visualizations
Chart generation functions for Streamlit display
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from config import (
    NOFAR_PURPLE, NOFAR_YELLOW, SOLAR_YELLOW, BESS_GREEN, 
    BESS_CHARGE_BLUE, GAP_RED, REVENUE_GREEN, COST_RED, 
    MARGIN_BLUE, HUB_GRAY, NODE_ORANGE, SUMMER_DAY, WINTER_DAY
)


def plot_daily_profile(model, day, block_mw, strike_price=None, title_suffix=""):
    """
    Create a 24-hour profile chart for a specific day.
    
    Shows:
    - Top panel: Generation stack (solar, BESS discharge, gap) + BESS charging
    - Bottom panel: Price curves (Hub, Node, VPPA effective revenue)
    """
    
    day_data = model[model['day_of_year'] == day].copy()
    
    if len(day_data) == 0:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.text(0.5, 0.5, f"No data for day {day}", ha='center', va='center')
        return fig
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[2, 1], sharex=True)
    
    hours = day_data['hour_of_day'].values
    solar = day_data['solar_gen_mw'].values
    bess_discharge = day_data['bess_discharge_mw'].values
    bess_charge = day_data['bess_charge_mw'].values
    gap = day_data['gap_mw'].values
    obligation = day_data['block_obligation_mw'].values
    hub_price = day_data['north_hub_price'].values
    node_price = day_data['lavender_node_price'].values
    solar_to_block = day_data['solar_to_block_mw'].values if 'solar_to_block_mw' in day_data.columns else day_data['solar_delivered_mw'].values
    solar_excess = day_data['solar_excess_mw'].values if 'solar_excess_mw' in day_data.columns else np.zeros(len(day_data))
    bess_to_block = day_data['bess_to_block_mw'].values if 'bess_to_block_mw' in day_data.columns else day_data['bess_discharge_mw'].values
    bess_excess = day_data['bess_excess_mw'].values if 'bess_excess_mw' in day_data.columns else np.zeros(len(day_data))
    
    # Get on-peak window from the data
    on_peak_hours = day_data[day_data['is_on_peak']]['hour_of_day']
    if len(on_peak_hours) > 0:
        start_hour = on_peak_hours.min()
        end_hour = on_peak_hours.max() + 1
    else:
        start_hour, end_hour = 7, 23
    
    # =========================================================================
    # TOP CHART: Generation Stack
    # =========================================================================
    
    # Stacked area for on-peak supply
    ax1.fill_between(hours, 0, solar_to_block, alpha=0.85, color=SOLAR_YELLOW, label='Solar to Block')
    ax1.fill_between(hours, solar_to_block, solar_to_block + solar_excess,
                    alpha=0.5, color=NOFAR_YELLOW, label='Solar Excess Merchant')
    ax1.fill_between(hours, solar_to_block, solar_to_block + bess_to_block,
                    alpha=0.8, color=BESS_GREEN, label='BESS to Block')
    ax1.fill_between(hours, solar_to_block + bess_to_block,
                    solar_to_block + bess_to_block + gap,
                    alpha=0.6, color=GAP_RED, label='Merchant Purchase')
    
    # BESS charging as negative bars
    ax1.bar(hours, -bess_charge, alpha=0.7, color=BESS_CHARGE_BLUE, label='BESS Charging', width=0.8)
    
    # Obligation line
    ax1.plot(hours, obligation, color=NOFAR_PURPLE, linewidth=3, linestyle='--', 
            label=f'{block_mw} MW Block')
    
    # Mark on-peak window
    ax1.axvspan(start_hour, end_hour, alpha=0.08, color='blue')
    ax1.axvline(x=start_hour, color='blue', linewidth=1, linestyle=':', alpha=0.5)
    ax1.axvline(x=end_hour, color='blue', linewidth=1, linestyle=':', alpha=0.5)
    
    ax1.axhline(y=0, color='black', linewidth=0.5)
    ax1.set_ylabel('Power (MW)', fontsize=11, fontweight='bold')
    ax1.set_title(f'24-Hour Profile {title_suffix}', fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax1.set_xlim(-0.5, 23.5)
    ax1.set_ylim(-130, max(block_mw + 50, solar.max() + 30))
    ax1.legend(loc='upper left', fontsize=8, ncol=2)
    ax1.grid(True, alpha=0.3)
    
    # Add on-peak label
    ax1.text((start_hour + end_hour) / 2, ax1.get_ylim()[1] * 0.93, 
             f'ON-PEAK ({start_hour}:00-{end_hour}:00)', 
             ha='center', fontsize=9, fontweight='bold', color='blue', alpha=0.7)
    
    # =========================================================================
    # BOTTOM CHART: Prices
    # =========================================================================
    
    ax2.plot(hours, hub_price, color=HUB_GRAY, linewidth=2, label='North Hub', marker='o', markersize=3)
    ax2.plot(hours, node_price, color=NODE_ORANGE, linewidth=2, label='Lavender Node', marker='s', markersize=3)
    
    if strike_price is not None:
        basis = node_price - hub_price
        vppa_effective = strike_price + basis
        ax2.plot(hours, vppa_effective, color=REVENUE_GREEN, linewidth=2, linestyle='--', 
                 label=f'VPPA Revenue (${strike_price:.0f}+Basis)')
    
    ax2.axvspan(start_hour, end_hour, alpha=0.08, color='blue')
    ax2.set_xlabel('Hour of Day', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Price ($/MWh)', fontsize=11, fontweight='bold')
    ax2.set_xlim(-0.5, 23.5)
    ax2.set_xticks(range(0, 24, 2))
    ax2.set_xticklabels([f'{h:02d}:00' for h in range(0, 24, 2)], rotation=45)
    ax2.legend(loc='upper left', fontsize=8)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig


def plot_sensitivity_curve(results, min_strike, target_margin, 
                           strike_min=40, strike_max=90, strike_step=2.5):
    """
    Plot strike price sensitivity curve showing margin vs strike price.
    """
    from analysis_engine import calculate_margin_at_strike
    
    strikes = np.arange(strike_min, strike_max + strike_step, strike_step)
    margins = [calculate_margin_at_strike(results, s) / 1e6 for s in strikes]  # Convert to millions
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Color bars based on whether they meet target
    target_m = target_margin / 1e6
    colors = [REVENUE_GREEN if m >= target_m else COST_RED for m in margins]
    
    ax.bar(strikes, margins, width=strike_step * 0.8, color=colors, alpha=0.7, edgecolor='black')
    
    # Target line
    ax.axhline(y=target_m, color=NOFAR_PURPLE, linewidth=2, linestyle='--', 
               label=f'Target: ${target_m:.1f}M')
    
    # Min strike marker
    ax.axvline(x=min_strike, color=MARGIN_BLUE, linewidth=2, linestyle='-',
               label=f'Min Strike: ${min_strike:.2f}')
    
    # Zero line
    ax.axhline(y=0, color='black', linewidth=0.5)
    
    ax.set_xlabel('VPPA Strike Price ($/MWh)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Net Margin ($ Millions)', fontsize=11, fontweight='bold')
    ax.set_title('Net Margin Sensitivity to Strike Price', fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3, axis='y')
    
    # Add annotation at min strike
    margin_at_min = calculate_margin_at_strike(results, min_strike) / 1e6
    ax.annotate(f'${min_strike:.2f}/MWh\n${margin_at_min:.1f}M', 
                xy=(min_strike, margin_at_min),
                xytext=(min_strike + 5, margin_at_min + 5),
                fontsize=9, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=MARGIN_BLUE))
    
    plt.tight_layout()
    return fig


def plot_volume_breakdown(results):
    """
    Create a pie chart showing volume breakdown by source.
    """
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    sizes = [results['solar_mwh'], results['bess_mwh'], results['merchant_mwh']]
    labels = [
        f"Solar\n{results['solar_mwh']/1000:.0f} GWh\n({results['solar_pct']:.0f}%)",
        f"BESS\n{results['bess_mwh']/1000:.0f} GWh\n({results['bess_pct']:.0f}%)",
        f"Merchant\n{results['merchant_mwh']/1000:.0f} GWh\n({results['merchant_pct']:.0f}%)"
    ]
    colors = [SOLAR_YELLOW, BESS_GREEN, GAP_RED]
    explode = (0.02, 0.02, 0.02)
    
    ax.pie(sizes, labels=labels, colors=colors, explode=explode,
           autopct='', startangle=90, textprops={'fontsize': 10, 'fontweight': 'bold'})
    
    ax.set_title(f"Volume Breakdown\nTotal: {results['block_volume']/1000:.0f} GWh", 
                 fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    
    return fig


def plot_bess_dispatch_pattern(model):
    """
    Create a chart showing BESS charge/discharge pattern by hour of day.
    """
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    # Average by hour of day
    charge_by_hour = model.groupby('hour_of_day')['bess_charge_mw'].mean()
    discharge_by_hour = model.groupby('hour_of_day')['bess_discharge_mw'].mean()
    
    hours = range(24)
    
    ax.bar(hours, -charge_by_hour.values, color=BESS_CHARGE_BLUE, alpha=0.8, label='Avg Charging')
    ax.bar(hours, discharge_by_hour.values, color=BESS_GREEN, alpha=0.8, label='Avg Discharging')
    
    ax.axhline(y=0, color='black', linewidth=0.5)
    
    # Mark typical on-peak (will be shaded based on actual data)
    on_peak_hours = model[model['is_on_peak']]['hour_of_day'].unique()
    if len(on_peak_hours) > 0:
        ax.axvspan(on_peak_hours.min(), on_peak_hours.max() + 1, alpha=0.1, color='blue')
    
    ax.set_xlabel('Hour of Day', fontsize=11, fontweight='bold')
    ax.set_ylabel('Average Power (MW)', fontsize=11, fontweight='bold')
    ax.set_title('BESS Charge/Discharge Pattern by Hour', fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig


def plot_economics_waterfall(results, min_strike):
    from analysis_engine import calculate_vppa_revenue_at_strike, calculate_margin_at_strike

    vppa_revenue = calculate_vppa_revenue_at_strike(results, min_strike) / 1e6
    merchant_sales = results['merchant_sales_revenue'] / 1e6
    market_cost = results['market_cost'] / 1e6
    bess_cost = results['bess_charge_cost'] / 1e6
    margin = calculate_margin_at_strike(results, min_strike) / 1e6

    fig, ax = plt.subplots(figsize=(11, 6))

    categories = [
        'VPPA\nRevenue',
        'Merchant\nSales',
        'Market\nPurchases',
        'BESS\nCharging',
        'Net\nMargin'
    ]
    x = np.arange(len(categories))

    ax.bar(0, vppa_revenue, color=REVENUE_GREEN, alpha=0.8, width=0.6)
    ax.text(0, vppa_revenue + 1, f'${vppa_revenue:.1f}M', ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.bar(1, merchant_sales, bottom=vppa_revenue, color=NOFAR_YELLOW, alpha=0.85, width=0.6)
    ax.text(1, vppa_revenue + merchant_sales/2, f'+${merchant_sales:.1f}M', ha='center', va='center',
            fontsize=10, fontweight='bold')

    after_revenues = vppa_revenue + merchant_sales

    ax.bar(2, market_cost, bottom=after_revenues - market_cost, color=COST_RED, alpha=0.8, width=0.6)
    ax.text(2, after_revenues - market_cost/2, f'-${market_cost:.1f}M', ha='center', va='center',
            fontsize=10, fontweight='bold', color='white')

    after_market = after_revenues - market_cost

    ax.bar(3, bess_cost, bottom=after_market - bess_cost, color=COST_RED, alpha=0.6, width=0.6)
    ax.text(3, after_market - bess_cost/2, f'-${bess_cost:.1f}M', ha='center', va='center',
            fontsize=10, fontweight='bold', color='white')

    ax.bar(4, margin, color=MARGIN_BLUE, alpha=0.8, width=0.6)
    ax.text(4, margin + 1, f'${margin:.1f}M', ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11, fontweight='bold')
    ax.set_ylabel('Amount ($ Millions)', fontsize=11, fontweight='bold')
    ax.set_title('VPPA Economics Waterfall', fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    return fig


def plot_monthly_breakdown(model, metric='gap_mw'):
    """
    Create a monthly breakdown chart for a given metric.
    """
    
    on_peak = model[model['is_on_peak']]
    
    monthly = model.groupby('month').agg({
        'solar_to_block_mw': 'sum',
        'solar_excess_mw': 'sum',
        'bess_to_block_mw': 'sum',
        'gap_mw': 'sum'
    }) / 1000
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    x = np.arange(12)
    bar_width = 0.6
    
    ax.bar(x, monthly['solar_to_block_mw'].values, bar_width, label='Solar to Block', color=SOLAR_YELLOW)
    ax.bar(x, monthly['solar_excess_mw'].values, bar_width,
        bottom=monthly['solar_to_block_mw'].values, label='Solar Excess Merchant', color=NOFAR_YELLOW)
    ax.bar(x, monthly['bess_to_block_mw'].values, bar_width,
        bottom=monthly['solar_to_block_mw'].values + monthly['solar_excess_mw'].values,
        label='BESS to Block', color=BESS_GREEN)
    ax.bar(x, monthly['gap_mw'].values, bar_width,
        bottom=monthly['solar_to_block_mw'].values + monthly['solar_excess_mw'].values + monthly['bess_to_block_mw'].values,
        label='Merchant Purchase', color=GAP_RED, alpha=0.7)
    
    ax.set_xlabel('Month', fontsize=11, fontweight='bold')
    ax.set_ylabel('Energy (GWh)', fontsize=11, fontweight='bold')
    ax.set_title('Monthly Volume Breakdown', fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.set_xticks(x)
    ax.set_xticklabels(months, rotation=45)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    return fig


def plot_price_comparison(model):
    """
    Create a chart comparing Hub, Lavender, and Fairway prices during on-peak hours.
    """
    
    on_peak = model[model['is_on_peak']]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    hourly_hub = on_peak.groupby('hour_of_day')['north_hub_price'].mean()
    hourly_lavender = on_peak.groupby('hour_of_day')['lavender_node_price'].mean()
    hourly_fairway = on_peak.groupby('hour_of_day')['fairway_node_price'].mean()
    
    hours = hourly_hub.index.values
    
    ax.plot(hours, hourly_hub.values, 'o-', color=HUB_GRAY, linewidth=2, markersize=6, label='North Hub')
    ax.plot(hours, hourly_lavender.values, 's-', color=NODE_ORANGE, linewidth=2, markersize=6, label='Lavender Node')
    ax.plot(hours, hourly_fairway.values, '^-', color=BESS_CHARGE_BLUE, linewidth=2, markersize=6, label='Fairway Node')
    
    ax.set_xlabel('Hour of Day', fontsize=11, fontweight='bold')
    ax.set_ylabel('Average Price ($/MWh)', fontsize=11, fontweight='bold')
    ax.set_title('On-Peak Price Comparison by Hour', fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig


# =============================================================================
# MULTI-YEAR FORECAST VISUALIZATIONS
# =============================================================================

from config import (
    DEGRADATION_COLOR, FORECAST_HUB_COLOR, FORECAST_LAVENDER_COLOR,
    FORECAST_FAIRWAY_COLOR, TARGET_LINE_COLOR, CUMULATIVE_MARGIN_COLOR,
    CUMULATIVE_TARGET_COLOR
)


def plot_annual_margin_vs_target(summary_df, strike_price):
    """
    Bar chart of annual net margin vs. escalating annual combined target.
    Bars are colored green if the year meets its target, red otherwise.
    """
    fig, ax = plt.subplots(figsize=(12, 5.5))

    years = summary_df['calendar_year'].values
    margins_m = summary_df['net_margin'].values / 1e6
    targets_m = summary_df['combined_target'].values / 1e6

    bar_colors = [REVENUE_GREEN if m >= t else COST_RED for m, t in zip(margins_m, targets_m)]

    x = np.arange(len(years))
    bars = ax.bar(x, margins_m, color=bar_colors, alpha=0.85, edgecolor='black', label='Net Margin')

    # Target line overlay
    ax.plot(x, targets_m, color=TARGET_LINE_COLOR, linewidth=2.5, marker='o',
            markersize=7, label='Combined Target (escalated)')

    # Value labels on top of bars
    for xi, m in zip(x, margins_m):
        ax.text(xi, m + max(margins_m) * 0.015, f'${m:.1f}M', ha='center', va='bottom',
                fontsize=8, fontweight='bold')

    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years], rotation=45)
    ax.set_xlabel('Contract Year', fontsize=11, fontweight='bold')
    ax.set_ylabel('Amount ($M)', fontsize=11, fontweight='bold')
    ax.set_title(f'Annual Net Margin vs. Escalated Target (Strike = ${strike_price:.2f}/MWh)',
                 fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    return fig


def plot_cumulative_trajectory(summary_df, strike_price, totals):
    """
    Cumulative net margin vs. cumulative combined target across the contract life.
    """
    fig, ax = plt.subplots(figsize=(11, 5.5))

    years = summary_df['calendar_year'].values
    cum_margin = np.cumsum(summary_df['net_margin'].values) / 1e6
    cum_target = np.cumsum(summary_df['combined_target'].values) / 1e6

    x = np.arange(len(years))

    ax.fill_between(x, 0, cum_margin, alpha=0.35, color=CUMULATIVE_MARGIN_COLOR,
                    label='Cumulative Margin')
    ax.plot(x, cum_margin, color=CUMULATIVE_MARGIN_COLOR, linewidth=2.5, marker='o')

    ax.plot(x, cum_target, color=CUMULATIVE_TARGET_COLOR, linewidth=2.5, linestyle='--',
            marker='s', label='Cumulative Target')

    # Annotations
    final_margin = cum_margin[-1]
    final_target = cum_target[-1]
    gap = final_margin - final_target
    color = REVENUE_GREEN if gap >= 0 else COST_RED
    ax.annotate(f'Final: ${final_margin:.1f}M\nTarget: ${final_target:.1f}M\nGap: ${gap:+.1f}M',
                xy=(x[-1], final_margin), xytext=(x[-1] - 3, final_margin * 0.55),
                fontsize=10, fontweight='bold', color=color,
                bbox=dict(boxstyle='round', facecolor='white', edgecolor=color, alpha=0.9))

    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years], rotation=45)
    ax.set_xlabel('Contract Year', fontsize=11, fontweight='bold')
    ax.set_ylabel('Cumulative Amount ($M)', fontsize=11, fontweight='bold')
    ax.set_title(f'Lifetime Margin Trajectory (Strike = ${strike_price:.2f}/MWh)',
                 fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig


def plot_annual_economics_stacked(summary_df, strike_price):
    """
    Stacked bar chart showing the full annual economics decomposition over the contract life.
    Revenues positive (VPPA + Merchant), costs negative (Market + BESS), net margin line.
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    years = summary_df['calendar_year'].values
    x = np.arange(len(years))

    vppa = summary_df['vppa_revenue'].values / 1e6
    merchant = summary_df['merchant_sales_revenue'].values / 1e6
    market_cost = summary_df['market_cost'].values / 1e6
    bess_cost = summary_df['bess_charge_cost'].values / 1e6
    margin = summary_df['net_margin'].values / 1e6

    width = 0.7

    # Positive stacks
    ax.bar(x, vppa, width, color=REVENUE_GREEN, alpha=0.85, label='VPPA Revenue')
    ax.bar(x, merchant, width, bottom=vppa, color=NOFAR_YELLOW, alpha=0.85, label='Merchant Sales')

    # Negative stacks
    ax.bar(x, -market_cost, width, color=COST_RED, alpha=0.85, label='Market Purchases')
    ax.bar(x, -bess_cost, width, bottom=-market_cost, color=COST_RED, alpha=0.55, label='BESS Charging')

    # Net margin line
    ax.plot(x, margin, color=MARGIN_BLUE, linewidth=2.5, marker='D', markersize=7,
            label='Net Margin', zorder=10)

    ax.axhline(y=0, color='black', linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years], rotation=45)
    ax.set_xlabel('Contract Year', fontsize=11, fontweight='bold')
    ax.set_ylabel('Amount ($M)', fontsize=11, fontweight='bold')
    ax.set_title(f'Annual Economics Breakdown (Strike = ${strike_price:.2f}/MWh)',
                 fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.legend(loc='upper left', fontsize=9, ncol=3)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    return fig


def plot_solar_degradation(summary_df, forecast_params):
    """
    Two-panel chart: degradation factor curve (top), annual solar generation in GWh (bottom).
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    years = summary_df['calendar_year'].values
    x = np.arange(len(years))

    # Top: degradation factor
    deg = summary_df['degradation_factor'].values * 100
    ax1.plot(x, deg, color=DEGRADATION_COLOR, linewidth=2.5, marker='o', markersize=7)
    ax1.fill_between(x, deg, alpha=0.15, color=DEGRADATION_COLOR)
    ax1.set_ylabel('Capacity Factor (%)', fontsize=11, fontweight='bold')
    ax1.set_title('Solar Module Degradation Over Contract Life',
                  fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax1.grid(True, alpha=0.3)

    # Annotate first and last
    ax1.annotate(f'Year 1: {deg[0]:.2f}%', xy=(x[0], deg[0]), xytext=(x[0] + 0.5, deg[0] - 1),
                 fontsize=9, fontweight='bold')
    ax1.annotate(f'Year {len(deg)}: {deg[-1]:.2f}%', xy=(x[-1], deg[-1]),
                 xytext=(x[-1] - 4, deg[-1] - 1), fontsize=9, fontweight='bold')

    # Add PVsyst default note
    y1_deg = forecast_params.get('first_year_degradation', 0) * 100
    ann_deg = forecast_params.get('annual_degradation', 0) * 100
    ax1.text(0.99, 0.05,
             f'First-year: {y1_deg:.2f}% | Annual: {ann_deg:.2f}%',
             transform=ax1.transAxes, ha='right', fontsize=8, style='italic',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    # Bottom: annual solar generation in GWh
    solar_gwh = summary_df['solar_mwh'].values / 1000
    solar_excess_gwh = summary_df['solar_excess_mwh'].values / 1000

    ax2.bar(x, solar_gwh, width=0.7, color=SOLAR_YELLOW, alpha=0.9, label='Solar to Block')
    ax2.bar(x, solar_excess_gwh, width=0.7, bottom=solar_gwh, color=NOFAR_YELLOW, alpha=0.65,
            label='Solar Excess (merchant)')

    ax2.set_xticks(x)
    ax2.set_xticklabels([str(y) for y in years], rotation=45)
    ax2.set_xlabel('Contract Year', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Annual Solar Generation (GWh)', fontsize=11, fontweight='bold')
    ax2.legend(loc='upper right', fontsize=9)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    return fig


def plot_price_forecast_trajectory(summary_df):
    """
    Line chart showing how the on-peak average prices evolve over contract years:
    North Hub, Lavender Node, and the Lavender basis.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    years = summary_df['calendar_year'].values
    x = np.arange(len(years))

    hub = summary_df['avg_hub_on_peak'].values
    lav = summary_df['avg_lavender_on_peak'].values
    basis = summary_df['avg_lavender_basis'].values

    # Top: absolute prices
    ax1.plot(x, hub, color=FORECAST_HUB_COLOR, linewidth=2.5, marker='o', markersize=6, label='North Hub')
    ax1.plot(x, lav, color=FORECAST_LAVENDER_COLOR, linewidth=2.5, marker='s', markersize=6,
             label='Lavender Node')

    # Highlight extended years
    extended_mask = summary_df['prices_extended'].values
    if extended_mask.any():
        ax1.axvspan(np.where(extended_mask)[0].min() - 0.5, x[-1] + 0.5,
                    alpha=0.12, color='orange', label='Extrapolated')

    ax1.set_ylabel('On-Peak Avg Price ($/MWh)', fontsize=11, fontweight='bold')
    ax1.set_title('Forecast Price Trajectory (On-Peak Averages)',
                  fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Bottom: Lavender basis
    colors = [REVENUE_GREEN if b >= 0 else COST_RED for b in basis]
    ax2.bar(x, basis, width=0.7, color=colors, alpha=0.8)
    ax2.axhline(y=0, color='black', linewidth=0.5)

    for xi, b in zip(x, basis):
        va = 'bottom' if b >= 0 else 'top'
        offset = max(abs(basis)) * 0.04 if b >= 0 else -max(abs(basis)) * 0.04
        ax2.text(xi, b + offset, f'${b:.1f}', ha='center', va=va, fontsize=7, fontweight='bold')

    ax2.set_xticks(x)
    ax2.set_xticklabels([str(y) for y in years], rotation=45)
    ax2.set_xlabel('Contract Year', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Lavender Basis ($/MWh)', fontsize=11, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    return fig


def plot_multiyear_sensitivity(sensitivity_df, min_strike, criterion_label,
                                lav_target_m, fair_target_m, discount_rate=None):
    """
    Strike-price sensitivity on lifetime totals. Shows undiscounted margin, NPV margin,
    and the number of years meeting the combined target, all against strike.
    """
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    strikes = sensitivity_df['strike_price'].values
    total_margin_m = sensitivity_df['total_margin'].values / 1e6
    npv_margin_m = sensitivity_df['npv_margin'].values / 1e6
    years_met = sensitivity_df['years_meeting_target'].values
    total_target_m = sensitivity_df['total_target'].iloc[0] / 1e6
    npv_target_m = sensitivity_df['npv_target'].iloc[0] / 1e6
    n_years = years_met.max() if len(years_met) else 0

    # Panel 1: Total undiscounted margin
    colors1 = [REVENUE_GREEN if m >= total_target_m else COST_RED for m in total_margin_m]
    axes[0].bar(strikes, total_margin_m, width=2, color=colors1, alpha=0.75, edgecolor='black')
    axes[0].axhline(total_target_m, color=TARGET_LINE_COLOR, linewidth=2, linestyle='--',
                    label=f'Target: ${total_target_m:.1f}M')
    axes[0].axvline(min_strike, color=MARGIN_BLUE, linewidth=2,
                    label=f'Min Strike: ${min_strike:.2f}')
    axes[0].set_xlabel('Strike ($/MWh)', fontsize=10, fontweight='bold')
    axes[0].set_ylabel('Lifetime Margin ($M)', fontsize=10, fontweight='bold')
    axes[0].set_title('Undiscounted Lifetime Margin', fontsize=11, fontweight='bold', color=NOFAR_PURPLE)
    axes[0].legend(fontsize=8, loc='upper left')
    axes[0].grid(True, alpha=0.3, axis='y')

    # Panel 2: NPV margin
    colors2 = [REVENUE_GREEN if m >= npv_target_m else COST_RED for m in npv_margin_m]
    axes[1].bar(strikes, npv_margin_m, width=2, color=colors2, alpha=0.75, edgecolor='black')
    axes[1].axhline(npv_target_m, color=TARGET_LINE_COLOR, linewidth=2, linestyle='--',
                    label=f'NPV Target: ${npv_target_m:.1f}M')
    axes[1].axvline(min_strike, color=MARGIN_BLUE, linewidth=2,
                    label=f'Min Strike: ${min_strike:.2f}')
    dr_label = f'(r={discount_rate*100:.1f}%)' if discount_rate is not None else ''
    axes[1].set_xlabel('Strike ($/MWh)', fontsize=10, fontweight='bold')
    axes[1].set_ylabel(f'Lifetime NPV Margin ($M) {dr_label}', fontsize=10, fontweight='bold')
    axes[1].set_title('Discounted Lifetime Margin', fontsize=11, fontweight='bold', color=NOFAR_PURPLE)
    axes[1].legend(fontsize=8, loc='upper left')
    axes[1].grid(True, alpha=0.3, axis='y')

    # Panel 3: Years meeting target
    axes[2].plot(strikes, years_met, color=NOFAR_PURPLE, linewidth=2.5, marker='o', markersize=5)
    axes[2].axhline(n_years, color=REVENUE_GREEN, linewidth=1.5, linestyle=':',
                    label=f'All {n_years} years')
    axes[2].axvline(min_strike, color=MARGIN_BLUE, linewidth=2,
                    label=f'Min Strike: ${min_strike:.2f}')
    axes[2].set_xlabel('Strike ($/MWh)', fontsize=10, fontweight='bold')
    axes[2].set_ylabel('# Years Meeting Target', fontsize=10, fontweight='bold')
    axes[2].set_title('Years Meeting Combined Target', fontsize=11, fontweight='bold', color=NOFAR_PURPLE)
    axes[2].legend(fontsize=8, loc='lower right')
    axes[2].grid(True, alpha=0.3)
    axes[2].set_ylim(-0.5, n_years + 0.5)

    fig.suptitle(f'Multi-Year Strike Sensitivity | Criterion: {criterion_label} | Targets: L=${lav_target_m:.0f}M F=${fair_target_m:.0f}M',
                 fontsize=12, fontweight='bold', color=NOFAR_PURPLE, y=1.02)

    plt.tight_layout()
    return fig


def plot_volume_mix_by_year(summary_df):
    """
    Stacked bar chart of annual volume contributions (Solar / BESS / Merchant) as a % of block.
    """
    fig, ax = plt.subplots(figsize=(11, 5))

    years = summary_df['calendar_year'].values
    x = np.arange(len(years))

    solar_pct = summary_df['solar_pct'].values
    bess_pct = summary_df['bess_pct'].values
    merchant_pct = summary_df['merchant_pct'].values

    ax.bar(x, solar_pct, width=0.7, color=SOLAR_YELLOW, alpha=0.9, label='Solar')
    ax.bar(x, bess_pct, width=0.7, bottom=solar_pct, color=BESS_GREEN, alpha=0.85, label='BESS')
    ax.bar(x, merchant_pct, width=0.7, bottom=solar_pct + bess_pct, color=GAP_RED, alpha=0.75,
           label='Merchant')

    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years], rotation=45)
    ax.set_xlabel('Contract Year', fontsize=11, fontweight='bold')
    ax.set_ylabel('Block Coverage (%)', fontsize=11, fontweight='bold')
    ax.set_title('Annual Block Coverage Mix',
                 fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax.legend(loc='upper right', fontsize=9)
    ax.set_ylim(0, 105)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    return fig


def plot_project_allocation_trajectory(summary_df):
    """
    Annual Lavender and Fairway margin allocation vs. their individual targets.
    Two-panel side-by-side.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), sharey=True)

    years = summary_df['calendar_year'].values
    x = np.arange(len(years))

    lav_alloc = summary_df['lavender_margin_alloc'].values / 1e6
    lav_target = summary_df['lavender_target'].values / 1e6
    fair_alloc = summary_df['fairway_margin_alloc'].values / 1e6
    fair_target = summary_df['fairway_target'].values / 1e6

    # Lavender
    lav_colors = [REVENUE_GREEN if a >= t else COST_RED for a, t in zip(lav_alloc, lav_target)]
    ax1.bar(x, lav_alloc, width=0.7, color=lav_colors, alpha=0.85, edgecolor='black', label='Lavender Margin')
    ax1.plot(x, lav_target, color=TARGET_LINE_COLOR, linewidth=2.5, marker='o',
             markersize=6, label='Lavender Target')
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(y) for y in years], rotation=45)
    ax1.set_xlabel('Contract Year', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Amount ($M)', fontsize=11, fontweight='bold')
    ax1.set_title('Lavender Solar', fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3, axis='y')

    # Fairway
    fair_colors = [REVENUE_GREEN if a >= t else COST_RED for a, t in zip(fair_alloc, fair_target)]
    ax2.bar(x, fair_alloc, width=0.7, color=fair_colors, alpha=0.85, edgecolor='black', label='Fairway Margin')
    ax2.plot(x, fair_target, color=TARGET_LINE_COLOR, linewidth=2.5, marker='o',
             markersize=6, label='Fairway Target')
    ax2.set_xticks(x)
    ax2.set_xticklabels([str(y) for y in years], rotation=45)
    ax2.set_xlabel('Contract Year', fontsize=11, fontweight='bold')
    ax2.set_title('Fairway BESS', fontsize=12, fontweight='bold', color=NOFAR_PURPLE)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    return fig
