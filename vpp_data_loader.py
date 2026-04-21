"""
VPPA Strike Forecast Analyzer - Data Loader
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
import streamlit as st

from config import (
    DATA_DIR,
    SOLAR_FILE,
    HUB_PRICE_FILE,
    LAVENDER_NODE_FILE,
    FAIRWAY_NODE_FILE,
    LAVENDER_CAPACITY_AC,
)


@st.cache_data
def load_solar_tmy():
    """
    Load the base 8760 TMY/PVsyst profile in MW.
    """
    filepath = os.path.join(DATA_DIR, SOLAR_FILE)

    try:
        df = pd.read_csv(filepath, sep=';', encoding='latin-1')
    except Exception:
        df = None

    energy_values = None

    if df is not None:
        df.columns = [str(c).strip() for c in df.columns]
        for col in df.columns:
            if 'E_Grid' in str(col):
                energy_values = pd.to_numeric(df[col], errors='coerce')
                break

    if energy_values is None:
        vals = []
        with open(filepath, 'r', encoding='latin-1', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or 'E_Grid' in line:
                    continue
                parts = line.split()
                try:
                    vals.append(float(parts[-1]))
                except Exception:
                    continue
        energy_values = pd.Series(vals, dtype='float64')

    solar_kw = energy_values.fillna(0.0).to_numpy(dtype=float)

    if len(solar_kw) < 8760:
        solar_kw = np.concatenate([solar_kw, np.zeros(8760 - len(solar_kw))])
    else:
        solar_kw = solar_kw[:8760]

    solar_mw = np.minimum(solar_kw / 1000.0, LAVENDER_CAPACITY_AC)

    result = pd.DataFrame({
        'hour_of_year': range(8760),
        'solar_gen_mw': solar_mw,
    })
    result['day_of_year'] = result['hour_of_year'] // 24 + 1
    result['hour_of_day'] = result['hour_of_year'] % 24
    result['month'] = pd.to_datetime(result['day_of_year'], format='%j').dt.month

    return result


@st.cache_data
def build_degraded_solar_profile(year_index: int, annual_degradation_rate: float):
    """
    Build a year-specific solar profile from the base TMY profile.

    year_index = 0 for the first operating year.
    """
    base = load_solar_tmy().copy()
    degradation_factor = (1 - annual_degradation_rate) ** year_index
    base['solar_gen_mw'] = base['solar_gen_mw'] * degradation_factor
    base['solar_degradation_factor'] = degradation_factor
    base['contract_year_index'] = year_index + 1
    return base


@st.cache_data
def read_csv_with_fallback(filepath, **kwargs):
    encodings = ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']
    last_error = None

    for enc in encodings:
        try:
            return pd.read_csv(filepath, encoding=enc, **kwargs)
        except UnicodeDecodeError as e:
            last_error = e
            continue

    raise last_error


@st.cache_data
def load_price_data(filename: str, year: int):
    filepath = os.path.join(DATA_DIR, filename)

    df = read_csv_with_fallback(filepath)
    df.columns = df.columns.str.strip().str.upper()

    price_col = 'ENERGY_PRICE'
    year_col = 'DATE_YEAR'

    if price_col not in df.columns:
        raise ValueError(f'Could not find {price_col} in {filename}')

    if year_col in df.columns:
        df[year_col] = pd.to_numeric(df[year_col], errors='coerce')
        df = df[df[year_col] == int(year)].copy()
    else:
        if 'DATE_TIME' not in df.columns:
            raise ValueError(f'Could not identify year or datetime columns in {filename}')
        df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], errors='coerce')
        df = df[df['DATE_TIME'].dt.year == int(year)].copy()

    if df.empty:
        raise ValueError(f'No price rows found for year {year} in {filename}')

    sort_cols = [c for c in ['DATE_TIME', 'TIME_HOUR', 'TIME_MINUTE'] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)

    prices = pd.to_numeric(df[price_col], errors='coerce').to_numpy(dtype=float)

    if len(prices) == 8784:
        prices = prices[:8760]
    elif len(prices) < 8760:
        raise ValueError(f'{filename} has only {len(prices)} rows for {year}, expected at least 8760')
    else:
        prices = prices[:8760]

    mean_val = np.nanmean(prices)
    if np.isnan(mean_val):
        raise ValueError(f'All prices are NaN in {filename} for {year}')

    return np.nan_to_num(prices, nan=mean_val)


@st.cache_data
def load_year_inputs(year: int, year_index: int, solar_degradation_rate: float):
    solar_df = build_degraded_solar_profile(year_index, solar_degradation_rate)
    hub_prices = load_price_data(HUB_PRICE_FILE, year)

    try:
        lavender_prices = load_price_data(LAVENDER_NODE_FILE, year)
    except Exception as e:
        st.warning(f'Could not load Lavender node prices for {year}: {e}. Using Hub prices.')
        lavender_prices = hub_prices.copy()

    try:
        fairway_prices = load_price_data(FAIRWAY_NODE_FILE, year)
    except Exception as e:
        st.warning(f'Could not load Fairway node prices for {year}: {e}. Using Hub prices.')
        fairway_prices = hub_prices.copy()

    return {
        'year': year,
        'year_index': year_index,
        'solar_df': solar_df,
        'hub_prices': hub_prices,
        'lavender_prices': lavender_prices,
        'fairway_prices': fairway_prices,
        'solar_degradation_factor': float(solar_df['solar_degradation_factor'].iloc[0]),
    }


@st.cache_data
def load_term_inputs(start_year: int, term_years: int, solar_degradation_rate: float):
    years = list(range(start_year, start_year + term_years))
    return {
        year: load_year_inputs(year, idx, solar_degradation_rate)
        for idx, year in enumerate(years)
    }


def validate_data(solar_df, hub_prices, lavender_prices, fairway_prices):
    results = {'valid': True, 'errors': [], 'warnings': []}

    if len(solar_df) != 8760:
        results['errors'].append(f'Solar data has {len(solar_df)} rows, expected 8760')
        results['valid'] = False

    if solar_df['solar_gen_mw'].isna().any():
        results['warnings'].append('Solar data contains NaN values')

    for name, prices in [('Hub', hub_prices), ('Lavender', lavender_prices), ('Fairway', fairway_prices)]:
        if len(prices) != 8760:
            results['errors'].append(f'{name} prices has {len(prices)} values, expected 8760')
            results['valid'] = False
        if np.isnan(prices).any():
            results['warnings'].append(f'{name} prices contain NaN values')
        if (prices < -500).any() or (prices > 5000).any():
            results['warnings'].append(f'{name} prices contain extreme values (outside -$500 to $5000)')

    return results


def _file_signature(filepath: str) -> tuple:
    """
    Return (size, mtime) for a file. Used as a cache key ingredient so that
    updating the CSV automatically busts the cache.
    """
    try:
        stat = os.stat(filepath)
        return (stat.st_size, stat.st_mtime)
    except OSError:
        return (0, 0.0)


@st.cache_data(show_spinner=False)
def _discover_years_from_file(filepath: str, signature: tuple):
    """
    Read a price CSV and return the sorted list of unique years present.

    `signature` (file size + mtime) is part of the cache key, so editing the
    file automatically busts the cache.
    """
    df = read_csv_with_fallback(filepath)
    df.columns = df.columns.str.strip().str.upper()

    # Prefer DATE_YEAR explicitly; it is unambiguous.
    if 'DATE_YEAR' in df.columns:
        years = pd.to_numeric(df['DATE_YEAR'], errors='coerce').dropna().unique().astype(int)
        if len(years) > 0:
            return sorted(years.tolist())

    # Next, any column that *looks* like a pure year column (not day/month of year).
    for col in df.columns:
        if 'YEAR' in col and 'DAY' not in col and 'MONTH' not in col and 'WEEK' not in col:
            try:
                years = pd.to_numeric(df[col], errors='coerce').dropna().unique().astype(int)
                # Sanity check: all values must be plausible calendar years
                if len(years) > 0 and years.min() > 1900 and years.max() < 2200:
                    return sorted(years.tolist())
            except Exception:
                continue

    # Finally, parse a datetime column.
    for col in df.columns:
        if 'DATE' in col or 'TIME' in col:
            dates = pd.to_datetime(df[col], errors='coerce')
            years = dates.dt.year.dropna().unique().astype(int)
            if len(years) > 0:
                return sorted(years.tolist())

    return []


def get_available_years():
    """
    Return the sorted list of years available in the hub price CSV.

    Cache-safe: uses the file's (size, mtime) as a cache key ingredient, so
    replacing the CSV on disk automatically invalidates the cached result
    without needing to restart the app or clear the Streamlit cache manually.
    """
    filepath = os.path.join(DATA_DIR, HUB_PRICE_FILE)
    signature = _file_signature(filepath)

    try:
        years = _discover_years_from_file(filepath, signature)
        if years:
            return years
    except Exception as e:
        st.warning(f'Could not discover years from {HUB_PRICE_FILE}: {e}')

    # Last-resort fallback only if everything above failed.
    return [2022, 2023, 2024, 2025]


@st.cache_data
def load_all_data(year: int):
    """
    Backward-compatible loader expected by app.py.
    Returns:
        solar_df, hub_prices, lavender_prices, fairway_prices
    """
    solar_df = load_solar_tmy()
    hub_prices = load_price_data(HUB_PRICE_FILE, year)

    try:
        lavender_prices = load_price_data(LAVENDER_NODE_FILE, year)
    except Exception as e:
        st.warning(f'Could not load Lavender node prices for {year}: {e}. Using Hub prices.')
        lavender_prices = hub_prices.copy()

    try:
        fairway_prices = load_price_data(FAIRWAY_NODE_FILE, year)
    except Exception as e:
        st.warning(f'Could not load Fairway node prices for {year}: {e}. Using Hub prices.')
        fairway_prices = hub_prices.copy()

    return solar_df, hub_prices, lavender_prices, fairway_prices
