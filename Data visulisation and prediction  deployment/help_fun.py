import os
import io
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import pandas as pd
import plotly.express as px


def load_csv_to_dataframe(file_storage) -> pd.DataFrame:
    """
    Load CSV file from file storage object into a pandas DataFrame
    Attempts to read with different encodings to handle various file formats
    """
    buffer = file_storage.read()
    # Try UTF-8 first, fallback to CP1252
    for encoding in ("utf-8", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(buffer), encoding=encoding)
        except Exception:
            continue
    # Final attempt: let pandas sniff
    return pd.read_csv(io.BytesIO(buffer))


def clean_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and preprocess the raw DataFrame
    - Normalizes column names
    - Drops empty columns
    - Trims string values
    - Attempts to parse dates
    """
    if raw_df is None:
        return raw_df
    # Normalize column names
    df = raw_df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    # Drop empty columns (all NaN)
    df = df.dropna(axis=1, how="all")
    # Trim string cells
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
    # Try to parse dates
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_datetime(df[col], errors="raise")
            except Exception:
                pass
    return df


def infer_column_kinds(df: pd.DataFrame) -> Dict[str, str]:
    """
    Infer the data type kind for each column in the DataFrame
    Returns mapping of column -> kind in {numeric, categorical, datetime, text}
    """
    # Return mapping of column -> kind in {numeric, categorical, datetime}.
    kinds: Dict[str, str] = {}
    for col in df.columns:
        dtype = df[col].dtype
        if pd.api.types.is_numeric_dtype(dtype):
            kinds[col] = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            kinds[col] = "datetime"
        else:
            # Heuristic: few unique values → categorical
            unique_count = df[col].nunique(dropna=True)
            kinds[col] = "categorical" if unique_count <= max(20, int(0.05 * len(df))) else "text"
    return kinds


# Function to build different types of charts using Plotly
def build_figure(
    df: pd.DataFrame,
    chart: str,
    x: Optional[str],
    y: Optional[str],
    
    title: str,
) -> "px.Figure":
    """
    Build a Plotly figure based on the specified chart type and parameters
    Supports line, bar, scatter, histogram, box, and pie charts
    """
    chart_type = (chart or "").strip().lower()  # normalize input

    if chart_type == "line":
        return px.line(df, x=x, y=y,  title=title)
    if chart_type == "bar":
        return px.bar(df, x=x, y=y,  title=title)
    if chart_type == "scatter":
        return px.scatter(df, x=x, y=y, title=title)
    if chart_type == "histogram":
        return px.histogram(df, x=x or y, title=title)
    if chart_type == "box":
        return px.box(df, x=x, y=y, title=title)
    if chart_type == "pie":
        if x and y:
            dfg = df.groupby(x, dropna=False)[y].sum().reset_index()
            return px.pie(dfg, names=x, values=y, title=title)
        return px.pie(df, names=x, title=title)
    raise ValueError(f"Unsupported chart type: {chart}")