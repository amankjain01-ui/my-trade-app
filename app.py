import streamlit as st
import pandas as pd
import yfinance as yf
import time
import random
import gspread
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go

# --- CONFIGURATION ---
st.set_page_config(page_title="ProTrade Ultra", layout="wide", page_icon="📈")
BROKERAGE_PER_ORDER = 500.0 

# --- MCX ASSETS (Yahoo Tickers + Correct Lot Sizes) ---
ASSETS = {
    "Gold (1 kg)":       {"ticker": "GC=F", "lot": 100},
    "Gold Mini":         {"ticker": "MGC=F", "lot": 10},  
    "Silver (30 kg)":    {"ticker": "SI=F", "lot": 30},
    "Silver Micro":      {"ticker": "SIL=F", "lot": 1},
    "Crude Oil":         {"ticker": "CL=F", "lot": 100},
    "Natural Gas":       {"ticker": "NG=F", "lot": 1250},
    "Copper":            {"ticker": "HG=F", "lot": 2500},
    "Zinc":              {"ticker": "ZNc1", "lot": 5000},
    "Aluminum":          {"ticker": "ALI=F", "lot": 5000},
    "Lead":              {"ticker": "Pb=F", "lot": 5000},
    "Mentha Oil":        {"ticker": "CMS=F", "lot": 360} # Global proxy
}

# --- DATABASE CONNECTION ---
def connect_db():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("My Trade DB")
    except Exception as e:
        st.error(f"Critical Database Error: {e}")
        st.stop()

# --- FETCH & UPDATE DATA ---
def get_users():
    try: return pd.DataFrame(connect_db().worksheet("Users").get_all_records())
    except: return pd.DataFrame()

def update_user_balance(username, new_balance):
    try:
        ws = connect_db().worksheet("Users")
        cell = ws.find(username)
        ws.update_cell(cell.row, 3, new_balance)
    except: pass

def log_trade(order_dict):
    connect_db().worksheet("Orders").append_row(list(order_dict.values()))

def update_portfolio(user, symbol, qty, price, action):
    ws = connect_db().worksheet("Portfolio")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    key = f"{user}_{symbol}"
    
    if not df.empty and key in df['User_Symbol'].values:
        row_idx = df.index[df['User_Symbol'] == key][0] + 2
        curr_qty = df.iloc[df.index[df['User_Symbol'] == key][0]]['Qty']
        
        if action == "BUY": new_qty = curr_qty + qty
        else: new_qty = curr_qty - qty
        
        if new_qty <= 0: ws.delete_rows(int(row_idx))
        else: ws.update_cell(int(row_idx), 4, int(new_qty))
    elif action == "BUY":
        ws.append_row([key, user, symbol, qty, price])

# --- PRO CHART ENGINE (MARKET PULSE STYLE) ---
def get_market_data(symbol, timeframe):
    ticker = ASSETS[symbol]["ticker"]
    period_map = {"1D": "1d", "5D": "5d", "1M": "1mo"}
    interval_map = {"1D": "5m", "5D": "15m", "1M": "1h"}
    
    try:
        data = yf.download(ticker, period=period_map[timeframe], interval=interval_map[timeframe], progress=False)
        if data.empty: return 0.0, None
        
        # Latest Price (with Simulation Noise for "Live" feel)
        base = data['Close'].iloc[-1].item()
        noise = base * 0.0002 
        live_price = base + random.uniform(-noise, noise)
        
        return round(live_price, 2), data
    except:
        return 0.0, None

def render_pro_chart(symbol, data):
    if data is None or data.empty:
        st.warning("Loading Chart Data...")
        return
        
    # Calculate SMA 20 (Simple Moving Average)
    data['SMA20'] = data['Close'].rolling(window=20).mean()

    # Create Candlestick
    fig = go.Figure()

    # 1. Candlestick Trace
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'], high=data['High'],
        low=data['Low'], close=data['Close'],
        name="Price",
        increasing_line_color='#26a69a', # Professional Green
        decreasing_line_color='#ef5350'  # Professional Red
    ))

    # 2. SMA Indicator Trace
    fig.add_trace(go.Scatter(
        x=data.index, y=data['SMA20'],
        mode='lines', name='SMA 20',
        line=dict(color='yellow', width=1.5)
    ))

    # 3. Layout Styling (Dark Mode / Market Pulse Look)
    fig.update_layout(
        title=f"<b>{symbol}</b>",
        xaxis_rangeslider_visible=False, # Remove bottom slider
        template="plotly_dark",
        height=550,
        margin=dict(l=10, r=10, t=40, b=10),
        yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
        xaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
        hovermode='x unified' # Crosshair behavior
    )
    
    st.plotly_chart(fig, use_container_width=True)

# --- LOGIN ---
if 'user' not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🔐 ProTrade Ultra</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True):
            df = get_users()
            if not df.empty and u in df['Username'].values:
                user_row = df[df['Username'] == u].iloc[0]
                if str(user_row['Password']) == str(p) and str(user_row['Active']).upper() == 'TRUE':
                    st.session_state.user = u
                    st.session_state.role = user_row['Role']
                    st.session_state.balance = float(user_row['Balance'])
                    st.rerun()
                else: st.error("Wrong Password")
            else: st.error("User Not Found")
    st.stop()

# --- HEADER & BALANCE ---
c1, c2 = st.columns([3, 1])
with c1:
    st.title(f"🚀 {st.session_state.user}'s Terminal")
with c2:
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# *** BIG BALANCE DISPLAY ***
st.markdown(f"""
    <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; border: 1px solid #333; text-align: center; margin-bottom: 20px;">
        <span style="color: #888; font-size: 14px;">AVAILABLE MARGIN</span><br>
        <span style="color: #4CAF50; font-size: 32px; font-weight: bold;">₹{st.session_state.balance:,.2f}</span>
    </div>
""", unsafe_allow_html=True)

# --- TABS ---
tab1, tab2 = st.tabs(["📊 Trade & Analysis", "💼 Portfolio & P&L"])

# === TAB 1: TRADING FLOOR ===
with tab1:
    col_left, col_right = st.columns([1, 2.5])
    
    with col_left:
        st.subheader("⚡ Order Panel")
        selected_asset = st.selectbox("Select Script", list(ASSETS.keys()))
        timeframe = st.selectbox("Timeframe", ["1D", "5D", "1M"])
        
        # Get Data
        usd_price, chart_data = get_market_data(selected_asset, timeframe)
        inr_price = usd_price * 84.0 # USD to INR
        
        # LIVE PRICE DISPLAY
        st.markdown(f"""
            <div style="font-size: 28px; font-weight: bold; color: #2196F3; margin-bottom: 10px;">
                {selected_asset}<br>
                ₹{inr_price:,.2f}
            </div>
        """, unsafe_allow_html=True)
        
        with st.form("trade_form"):
            qty = st.number_input("Lots", 1, 100, 1)
            action = st.radio("Side", ["BUY", "SELL"], horizontal=True)
            
            lot_size = ASSETS[selected_asset]["lot"]
            trade_val = inr_price * qty * lot_size
            
            st.caption(f"Lot Size: {lot_size} | Value: ₹{trade_val:,.0f}")
            
            if st.form_submit_button("PLACE ORDER", use_container_width=True):
                cost = trade_val + BROKERAGE_PER_ORDER if action == "BUY" else trade_val - BROKERAGE_PER_ORDER
                
                if action == "BUY" and st.session_state.balance < cost:
                    st.error("Insufficient Funds!")
                else:
                    new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
                    update_user_balance(st.session_state.user, new_bal)
                    log_trade({
                        'Time': time.strftime("%Y-%m-%d %H:%M:%S"), 'User': st.session_state.user,
                        'Symbol': selected_asset, 'Action': action, 'Qty': qty,
                        'Price': inr_price, 'Value': trade_val, 'Fees': BROKERAGE_PER_ORDER
                    })
                    update_portfolio(st.session_state.user, selected_asset, qty, inr_price, action)
                    st.session_state.balance = new_bal
                    st.success("Order Executed!")
                    time.sleep(1)
                    st.rerun()

    with col_right:
        # RENDER THE PRO CHART
        render_pro_chart(selected_asset, chart_data)
        if st.button("🔄 Refresh Chart"):
            st.rerun()

# === TAB 2: PORTFOLIO ===
with tab2:
    st.subheader("Live Positions")
    try:
        ws = connect_db().worksheet("Portfolio")
        data = ws.get_all_records()
        df_port = pd.DataFrame(data)
    except: df_port = pd.DataFrame()

    if not df_port.empty:
        my_port = df_port[df_port['User'] == st.session_state.user]
        if not my_port.empty:
            total_pnl = 0.0
            pnl_rows = []
            
            for i, row in my_port.iterrows():
                sym = row['Symbol']
                qty = row['Qty']
                buy_avg = row['Avg_Price']
                
                curr_usd, _ = get_market_data(sym, "1D")
                curr_inr = curr_usd * 84.0
                lot = ASSETS[sym]["lot"]
                
                pnl = (curr_inr - buy_avg) * qty * lot
                total_pnl += pnl
                
                color = "green" if pnl >= 0 else "red"
                pnl_rows.append({
                    "Script": sym, "Qty": qty, "Buy Avg": f"₹{buy_avg:,.2f}",
                    "LTP": f"₹{curr_inr:,.2f}", "P&L": pnl
                })
                
            st.dataframe(pd.DataFrame(pnl_rows).style.format({"P&L": "₹{:.2f}"}))
            
            # TOTAL P&L CARD
            pnl_color = "#4CAF50" if total_pnl >= 0 else "#ef5350"
            st.markdown(f"""
                <div style="background-color: #1e1e1e; padding: 20px; border-radius: 10px; border: 1px solid {pnl_color}; text-align: center; margin-top: 20px;">
                    <span style="color: #fff; font-size: 18px;">TOTAL P&L</span><br>
                    <span style="color: {pnl_color}; font-size: 36px; font-weight: bold;">₹{total_pnl:,.2f}</span>
                </div>
            """, unsafe_allow_html=True)
            
            if st.button("Refresh P&L"): st.rerun()
        else: st.info("No open positions.")
    else: st.info("No open positions.")
