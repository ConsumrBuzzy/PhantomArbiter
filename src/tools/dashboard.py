
import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
import time
import os
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="Phantom Trader HUD", page_icon="🛸", layout="wide")

# Paths (Relative to root)
CACHE_FILE = os.path.join("data", "price_cache.json")
POSITIONS_FILE = os.path.join("data", "positions.json")
REFRESH_RATE = 2  # Seconds

# --- HELPER FUNCTIONS ---
def load_data():
    """Reads the JSON state files safely."""
    market_data = {}
    positions = {}
    
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                market_data = json.load(f)
                
            # V8.1: Load positions from broker wallet cache if available
            if 'wallet' in market_data and 'held_assets' in market_data['wallet']:
                raw_assets = market_data['wallet']['held_assets']
                for symbol, data in raw_assets.items():
                    positions[symbol] = {
                        'amount': data.get('balance', 0),
                        'entry_price': 0.0,  # Broker doesn't track entry yet
                        'value': data.get('value_usd', 0)
                    }
        except Exception:
            pass
        
    return market_data, positions

def calculate_rsi(prices, period=14):
    """Quick RSI calc for the chart view."""
    if len(prices) < period:
        return 50
    df = pd.DataFrame(prices, columns=['close'])
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    if loss.iloc[-1] == 0:
        return 100 if gain.iloc[-1] > 0 else 50
        
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

# --- MAIN HUD LAYOUT ---
st.title("🛸 Phantom Trader V8.1 // Command Deck")

# Auto-Refresh Loop hack for Streamlit
if 'last_update' not in st.session_state:
    st.session_state.last_update = time.time()

market_data, positions = load_data()

# 1. TOP BAR: PLAYER STATS (Portfolio Health)
pocket_cash = 0.0
bag_value = 0.0

if 'wallet' in market_data:
    pocket_cash = market_data['wallet'].get('usdc', 0.0)

current_prices = {}
if 'prices' in market_data:
    for ticker, data in market_data['prices'].items():
        current_prices[ticker] = data.get('price', 0)

if positions:
    bag_value = sum([p['amount'] * current_prices.get(t, 0) for t, p in positions.items()])

total_hp = pocket_cash + bag_value
start_hp = 14.34 # Original seed capital

col1, col2, col3, col4 = st.columns(4)
col1.metric("❤️ Total HP (Portfolio)", f"${total_hp:.2f}", delta=f"{((total_hp/start_hp)-1)*100:.1f}%")
col2.metric("💧 Mana (Liquid USDC)", f"${pocket_cash:.2f}")
col3.metric("🎒 Inventory Value", f"${bag_value:.2f}")
col4.metric("📡 Data Link", "ONLINE" if market_data else "OFFLINE")

st.markdown("---")

# 2. MAIN VIEW: LIVE CHARTS & TARGETS
# Create tabs for different views
tab1, tab2 = st.tabs(["📈 Market Scan", "🎒 Inventory (Positions)"])

with tab1:
    # Display Watchers
    prices_data = market_data.get("prices", {})
    
    if not prices_data:
        st.warning("No market data received yet.")
    else:
        # Grid layout for charts - dynamically create rows
        tickers = list(prices_data.keys())
        
        # Split into rows of 3
        for i in range(0, len(tickers), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(tickers):
                    ticker = tickers[i + j]
                    with cols[j]:
                        data = prices_data[ticker]
                        
                        # Handle missing price/history gracefully
                        curr_price = data.get('price', 0)
                        hist_data = data.get('history', [])
                        price_hist = [p['price'] for p in hist_data] if hist_data else []
                        
                        # Draw Mini-Chart if we have history
                        if len(price_hist) > 10:
                            # Verify price logic
                            start_p = price_hist[-2] if len(price_hist) > 1 else price_hist[0]
                            end_p = price_hist[-1]
                            color = '#00ff00' if end_p >= start_p else '#ff0000'
                            
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(y=price_hist, mode='lines', name='Price', line=dict(color=color, width=2)))
                            fig.update_layout(
                                title=f"{ticker}: ${curr_price:.4f}",
                                margin=dict(l=0, r=0, t=30, b=0),
                                height=200,
                                showlegend=False,
                                paper_bgcolor='rgba(0,0,0,0)',
                                plot_bgcolor='rgba(0,0,0,0)',
                                xaxis=dict(showgrid=False, showticklabels=False),
                                yaxis=dict(showgrid=True, gridcolor='#333333')
                            )
                            st.plotly_chart(fig)
                            
                            # Signal Status
                            rsi_val = calculate_rsi(price_hist)
                            
                            status_color = "white"
                            status_icon = "⚪"
                            status_text = "HOLD"
                            
                            if rsi_val < 30:
                                status_color = "green"
                                status_icon = "🟢"
                                status_text = "BUY SIGNAL"
                            elif rsi_val > 70:
                                status_color = "red"
                                status_icon = "🔴"
                                status_text = "OVERBOUGHT"
                                
                            st.markdown(f"**RSI:** {rsi_val:.1f} | **Status:** :{status_color}[{status_text}]")

with tab2:
    if not positions:
        st.info("Inventory Empty. Scanning for loot...")
        if 'wallet' in market_data:
            st.caption(f"Raw Wallet Data: {market_data['wallet'].get('held_assets', '{}')}")
            st.caption(f"Keys Found: {list(market_data.get('prices', {}).keys())}")
    else:
        for ticker, data in positions.items():
            curr_price = current_prices.get(ticker, 0)
            entry = data.get('entry_price', 0)
            amt = data.get('amount', 0)
            
            if entry > 0:
                pnl_pct = ((curr_price - entry) / entry) * 100
            else:
                pnl_pct = 0.0
            
            # Position Card
            with st.container():
                st.markdown(f"### 🛡️ {ticker}")
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"Entry: ${entry:.4f}")
                c2.write(f"Current: ${curr_price:.4f}")
                c3.metric("PnL", f"{pnl_pct:.2f}%")
                c4.write(f"Value: ${amt * curr_price:.2f}")
                
                # Visual bar for PnL (Normalize -10% to +10% range to 0.0-1.0)
                progress = min(max((pnl_pct + 10) / 20, 0.0), 1.0)
                st.progress(progress)
                st.markdown("---")

# Refresh Logic
time.sleep(REFRESH_RATE)
st.rerun()
