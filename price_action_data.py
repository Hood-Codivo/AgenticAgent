import pandas as pd


def preprocess_ohlcv_dataframe(df: pd.DataFrame):
    """
    Preprocess OHLCV data for pure price-action analysis.

    Expected columns: [Gmt time, Open, High, Low, Close, Volume]
    """
    df.columns = df.columns.str.strip()

    if "Gmt time" in df.columns:
        df["Gmt time"] = pd.to_datetime(df["Gmt time"], errors="coerce", dayfirst=True)
        df = df.set_index("Gmt time")
    else:
        df.index = pd.to_datetime(df.index, errors="coerce")

    df.sort_index(inplace=True)

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df.dropna(inplace=True)
    feature_cols = ["Open", "High", "Low", "Close", "Volume"]

    return df, feature_cols


def load_and_preprocess_data(csv_path: str):
    """Loads OHLCV data from CSV and preprocesses it for pure price action."""
    df = pd.read_csv(csv_path)
    return preprocess_ohlcv_dataframe(df)
