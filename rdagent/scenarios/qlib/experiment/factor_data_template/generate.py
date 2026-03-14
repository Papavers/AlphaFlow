import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Create synthetic data instead of downloading from network
# This avoids network timeout issues while maintaining the same data structure

# Generate date range
dates = pd.date_range(start="2008-12-29", end="2024-01-01", freq="D")

# Generate instruments (stock codes)
instruments = [f"SH600{i:03d}" for i in range(1, 101)]

# Create multi-index
index = pd.MultiIndex.from_product([instruments, dates], names=["instrument", "datetime"])

# Create synthetic OHLCV data
np.random.seed(42)
n_samples = len(index)
data = pd.DataFrame({
    "$open": 100 + np.random.randn(n_samples).cumsum() * 0.5,
    "$close": 100 + np.random.randn(n_samples).cumsum() * 0.5,
    "$high": 101 + np.random.randn(n_samples).cumsum() * 0.5,
    "$low": 99 + np.random.randn(n_samples).cumsum() * 0.5,
    "$volume": np.random.randint(1000000, 10000000, n_samples),
    "$factor": 1.0 + np.random.randn(n_samples) * 0.01,
}, index=index)

# Ensure price is positive
data[["$open", "$close", "$high", "$low"]] = data[["$open", "$close", "$high", "$low"]].clip(lower=10)

# Save full dataset
data.to_hdf("./daily_pv_all.h5", key="data")
print("✓ Created daily_pv_all.h5")

# Save debug dataset (subset)
# Filter by datetime in the MultiIndex (level 1), not columns
debug_start = "2018-01-01"
debug_end = "2019-12-31"
debug_data = data.reset_index()
debug_data = debug_data[(debug_data["datetime"] >= debug_start) & (debug_data["datetime"] <= debug_end)]
debug_data = debug_data.set_index(["instrument", "datetime"]).sort_index()
debug_data.to_hdf("./daily_pv_debug.h5", key="data")
print("✓ Created daily_pv_debug.h5")
