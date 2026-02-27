#!/bin/bash
# Build script for Render deployment
# This ensures kaleido is properly installed

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Verifying kaleido installation..."
python -c "import kaleido; print('Kaleido version:', kaleido.__version__)"

echo "Testing plotly with kaleido..."
python -c "import plotly.graph_objects as go; fig = go.Figure(); fig.add_trace(go.Scatter(x=[1,2,3], y=[4,5,6])); import plotly.io as pio; pio.kaleido.scope.default_format = 'png'; print('Kaleido initialized successfully')"

echo "Build completed successfully!"

