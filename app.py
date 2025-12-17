import streamlit as st
import pandas as pd
import yfinance as yf
import time
import random
import gspread
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go

# --- CONFIGURATION ---
st.set_page_config(page_title="ProTrade Max", layout="wide", page_icon="🚀")
BROKERAGE_PER_ORDER = 500.0 

# --- ASSET DATABASE (Global Proxies for MCX) ---
# Format: "Name": {"ticker": "YahooSymbol", "lot_size": MCX_Lot_Size}
ASSETS = {
    "Gold":        {"ticker": "GC=F", "lot": 100},
    "Silver":      {"ticker": "SI=F", "lot": 30},
    "Crude Oil":   {"ticker": "CL=F", "lot": 100},
    "Natural Gas": {"ticker": "NG=F", "lot": 1250},
    "Copper":      {"ticker": "HG=F", "lot": 2500},
    "Zinc":        {"ticker": "ZNc1", "lot": 5000}, # ZNc1 often tricky on Yahoo, using simul if fails
    "Aluminum":    {"ticker": "ALI=F", "lot": 5000},
    "Lead":        {"ticker": "Pb=F", "lot": 5000}
}

# --- CONNECT TO DATABASE ---
def connect_db():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("My Trade DB")
    except Exception as e:
        st.error(f"Database Error: {e}")
        st.stop()

# --- FETCH & UPDATE FUNCTIONS ---
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

# --- LIVE PRICE & CHART ENGINE ---
def get_live_data(symbol):
    ticker = ASSETS[symbol]["ticker"]
    try:
        # Get Intraday data for Chart
        data = yf.download(ticker, period="1d", interval="15m", progress=False)
        if data.empty: return 0.0, None
        
        # Current Price
        base_price = data['Close'].iloc[-1].item() # .item() converts numpy to float
        
        # Add "Simulation Noise" to keep it ticking
        noise = base_price * 0.0003 
        live_price = base_price + random.uniform(-noise, noise)
        
        return round(live_price, 2), data
    except:
        return 0.0, None

def render_chart(symbol, data):
    if data is None or data.empty:
        st.warning("Chart data unavailable")
        return
        
    fig = go.Figure(data=[go.Candlestick(
        x=data.index,
        open=data['Open'],
        high=data['High'],
        low=data['Low'],
        close=data['Close'],
        name=symbol
    )])
    fig.update_layout(
        title=f"{symbol} Intraday Chart",
        yaxis_title="Price (USD)",
        xaxis_title="Time",
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=0, t=30, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)

# --- APP LOGIN ---
if 'user' not in st.session_state:
    st.title("🔐 ProTrade Max Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        df = get_users()
        if not df.empty and u in df['Username'].values:
            user_row = df[df['Username'] == u].iloc[0]
            if str(user_row['Password']) == str(p) and str(user_row['Active']).upper() == 'TRUE':
                st.session_state.user = u
                st.session_state.role = user_row['Role']
                st.session_state.balance = float(user_row['Balance'])
                st.rerun()
            else: st.error("Access Denied")
        else: st.error("User Not Found")
    st.stop()

# --- SIDEBAR ---
st.sidebar.title(f"👤 {st.session_state.user}")
st.sidebar.caption(f"Wallet: ₹{st.session_state.balance:,.0f}")
if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.rerun()

# --- MAIN APP ---
st.title("🚀 ProTrade Terminal")

# Tabs for Organization
tab1, tab2 = st.tabs(["📈 Trade & Charts", "💼 Live Portfolio (P&L)"])

# === TAB 1: TRADING ===
with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Market Watch")
        selected_asset = st.selectbox("Select Script", list(ASSETS.keys()))
        
        # Get Data
        usd_price, chart_data = get_live_data(selected_asset)
        inr_price = usd_price * 84.0 # Fixed USD-INR multiplier
        
        st.metric(label=f"{selected_asset} LIVE", value=f"₹{inr_price:,.2f}")
        
        # Order Form
        with st.form("order_form"):
            qty = st.number_input("Lots", 1, 50, 1)
            action = st.radio("Action", ["BUY", "SELL"], horizontal=True)
            
            lot_size = ASSETS[selected_asset]["lot"]
            trade_value = inr_price * qty * lot_size
            
            st.write(f"Lot Size: {lot_size}")
            st.write(f"**Total Value: ₹{trade_value:,.0f}**")
            
            submitted = st.form_submit_button("⚡ EXECUTE TRADE")
            
            if submitted:
                # Calc Charges
                total_cost = trade_value + BROKERAGE_PER_ORDER if action == "BUY" else trade_value - BROKERAGE_PER_ORDER
                
                if action == "BUY" and st.session_state.balance < total_cost:
                    st.error("Insufficient Funds")
                else:
                    new_bal = st.session_state.balance - total_cost if action == "BUY" else st.session_state.balance + total_cost
                    
                    # Update DB
                    update_user_balance(st.session_state.user, new_bal)
                    log_trade({
                        'Time': time.strftime("%Y-%m-%d %H:%M:%S"),
                        'User': st.session_state.user,
                        'Symbol': selected_asset,
                        'Action': action,
                        'Qty': qty,
                        'Price': inr_price,
                        'Value': trade_value,
                        'Brokerage': BROKERAGE_PER_ORDER
                    })
                    update_portfolio(st.session_state.user, selected_asset, qty, inr_price, action)
                    
                    st.session_state.balance = new_bal
                    st.success("Trade Executed!")
                    time.sleep(1)
                    st.rerun()

    with col2:
        st.subheader("Live Chart")
        render_chart(selected_asset, chart_data)
        if st.button("🔄 Refresh Data"):
            st.rerun()

# === TAB 2: LIVE PORTFOLIO ===
with tab2:
    st.subheader("💼 Open Positions & P&L")
    
    # 1. Fetch Portfolio from Sheet
    try:
        ws = connect_db().worksheet("Portfolio")
        data = ws.get_all_records()
        df_port = pd.DataFrame(data)
    except: df_port = pd.DataFrame()

    if df_port.empty:
        st.info("No open positions.")
    else:
        # Filter for current user
        my_port = df_port[df_port['User'] == st.session_state.user]
        
        if my_port.empty:
            st.info("No open positions.")
        else:
            total_pnl = 0.0
            
            # Create a display table
            pnl_data = []
            
            for index, row in my_port.iterrows():
                symbol = row['Symbol']
                buy_price = float(row['Avg_Price'])
                qty = int(row['Qty'])
                lot_size = ASSETS.get(symbol, {}).get("lot", 1)
                
                # Fetch Current Price Live
                curr_usd, _ = get_live_data(symbol)
                curr_inr = curr_usd * 84.0
                
                # Calc P&L
                # Formula: (Current - Buy) * Qty * LotSize
                pnl = (curr_inr - buy_price) * qty * lot_size
                total_pnl += pnl
                
                pnl_data.append({
                    "Script": symbol,
                    "Qty (Lots)": qty,
                    "Buy Price": f"₹{buy_price:,.2f}",
                    "Curr Price": f"₹{curr_inr:,.2f}",
                    "P&L": pnl
                })
            
            # Show Table
            st.dataframe(pd.DataFrame(pnl_data).style.format({"P&L": "₹{:.2f}"}))
            
            # Show Total Big Metric
            color = "normal"
            if total_pnl > 0: color = "normal" # Streamlit handles green/red in metric delta automatically
            
            st.metric(label="TOTAL UNREALIZED P&L", value=f"₹{total_pnl:,.2f}", delta=total_pnl)
            
            if st.button("🔄 Update P&L"):
                st.rerun()
