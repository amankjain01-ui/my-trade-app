import streamlit as st
import pandas as pd
import yfinance as yf
import time
import random
import gspread
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# --- PAGE CONFIGURATION (Browser Tab) ---
st.set_page_config(
    page_title="Kite Pro", 
    layout="wide", 
    page_icon="🪁",
    initial_sidebar_state="expanded"
)

# --- THEME INJECTION (ZERODHA/GROWW DARK MODE) ---
st.markdown("""
    <style>
        /* Main Background */
        .stApp { background-color: #0e0e0e; color: #e0e0e0; }
        
        /* Sidebar */
        [data-testid="stSidebar"] { background-color: #161616; border-right: 1px solid #333; }
        
        /* Inputs */
        .stTextInput input, .stNumberInput input, .stSelectbox div { 
            background-color: #262626 !important; 
            color: white !important; 
            border: 1px solid #444 !important; 
        }
        
        /* Buttons */
        .stButton button {
            width: 100%;
            border-radius: 4px;
            font-weight: bold;
            border: none;
        }
        
        /* Metrics */
        [data-testid="stMetricValue"] { font-family: 'Roboto', sans-serif; font-weight: 700; }
        
        /* Custom Cards */
        .card {
            background-color: #1e1e1e;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #333;
            margin-bottom: 10px;
        }
        
        /* Green/Red Text */
        .text-green { color: #2ecc71; }
        .text-red { color: #e74c3c; }
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
BROKERAGE_PER_ORDER = 500.0 
ASSETS = {
    "Gold":       {"ticker": "GC=F", "lot": 100},
    "Gold Mini":  {"ticker": "MGC=F", "lot": 10},
    "Silver":     {"ticker": "SI=F", "lot": 30},
    "Crude Oil":  {"ticker": "CL=F", "lot": 100},
    "Natural Gas":{"ticker": "NG=F", "lot": 1250},
    "Copper":     {"ticker": "HG=F", "lot": 2500},
    "Zinc":       {"ticker": "ZNc1", "lot": 5000},
    "Nifty 50":   {"ticker": "^NSEI", "lot": 50},  # Added Index for reference
    "Bank Nifty": {"ticker": "^NSEBANK", "lot": 15}
}

# --- DATABASE CONNECTION ---
def connect_db():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("My Trade DB")
    except Exception as e:
        st.error(f"DB Error: {e}")
        st.stop()

# --- DATA FUNCTIONS ---
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

# --- PRO CHART ENGINE (TradingView Style) ---
def get_market_data(symbol, period="1d", interval="5m"):
    ticker = ASSETS[symbol]["ticker"]
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        if data.empty: return 0.0, None
        
        # Live Price Simulation
        base = data['Close'].iloc[-1].item()
        noise = base * 0.0001
        live_price = base + random.uniform(-noise, noise)
        
        return round(live_price, 2), data
    except: return 0.0, None

def render_chart(symbol, data):
    if data is None or data.empty:
        st.warning("Chart loading...")
        return
    
    # Create Subplots (Price Top, Volume Bottom)
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f"{symbol}", "Volume"),
                        row_heights=[0.7, 0.3])

    # 1. Candlestick
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'], high=data['High'],
        low=data['Low'], close=data['Close'],
        name="Price",
        increasing_line_color='#00d09c', # Groww Green
        decreasing_line_color='#eb5b3c'  # Groww Red
    ), row=1, col=1)

    # 2. Volume Bar
    colors = ['#00d09c' if c >= o else '#eb5b3c' for c, o in zip(data['Close'], data['Open'])]
    fig.add_trace(go.Bar(
        x=data.index, y=data['Volume'],
        marker_color=colors,
        name="Volume"
    ), row=2, col=1)

    # Styling
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1e1e1e",
        plot_bgcolor="#1e1e1e",
        height=500,
        margin=dict(l=0, r=40, t=30, b=0),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        showlegend=False
    )
    fig.update_yaxes(gridcolor="#333", side="right") # Price scale on right like TradingView
    fig.update_xaxes(gridcolor="#333")

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# --- LOGIN SYSTEM ---
if 'user' not in st.session_state:
    st.markdown("<br><br><h1 style='text-align: center; color: #00d09c;'>🪁 Kite Pro Login</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Login to Terminal"):
                df = get_users()
                if not df.empty and u in df['Username'].values:
                    user_row = df[df['Username'] == u].iloc[0]
                    if str(user_row['Password']) == str(p) and str(user_row['Active']).upper() == 'TRUE':
                        st.session_state.user = u
                        st.session_state.role = user_row['Role']
                        st.session_state.balance = float(user_row['Balance'])
                        st.rerun()
                    else: st.error("Incorrect Password")
                else: st.error("User ID not found")
    st.stop()

# --- SIDEBAR (Market Watch) ---
with st.sidebar:
    st.header(f"👤 {st.session_state.user}")
    
    # Auto-Refresh Toggle
    auto_refresh = st.checkbox("🔴 Auto-Refresh (Live Mode)", value=False)
    if auto_refresh:
        st_autorefresh(interval=2000, key="data_refresh") # Refresh every 2 seconds

    st.divider()
    
    # Watchlist
    st.caption("WATCHLIST")
    for asset, details in ASSETS.items():
        price, _ = get_market_data(asset, "1d", "1h") # Fast fetch
        inr_price = price * 84.0
        
        # Colored change (Simulated for look)
        change = random.uniform(-0.5, 0.5)
        color = "#00d09c" if change > 0 else "#eb5b3c"
        
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{asset}**")
        c2.markdown(f"<span style='color:{color}'>₹{inr_price:,.0f}</span>", unsafe_allow_html=True)
    
    st.divider()
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- MAIN DASHBOARD ---
# Top Balance Bar
st.markdown(f"""
    <div class="card" style="display: flex; justify_content: space-between; align-items: center;">
        <div>
            <span style="color: #888;">Available Margin</span>
            <h2 style="color: #00d09c; margin: 0;">₹{st.session_state.balance:,.2f}</h2>
        </div>
        <div>
            <span style="color: #888;">Status</span>
            <h4 style="color: #00d09c; margin: 0;">● CONNECTED</h4>
        </div>
    </div>
""", unsafe_allow_html=True)

# Main Workspace
col_chart, col_order = st.columns([3, 1])

with col_chart:
    # Asset Selector Header
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        selected_asset = st.selectbox("Symbol", list(ASSETS.keys()), label_visibility="collapsed")
    with c2:
        timeframe = st.selectbox("Time", ["1D", "5D", "1M"], label_visibility="collapsed")
    
    # Get Data & Render Chart
    usd_price, chart_data = get_market_data(selected_asset, timeframe)
    inr_price = usd_price * 84.0
    
    # Big Price Header
    st.markdown(f"<h1 style='margin:0;'>₹{inr_price:,.2f} <span style='font-size: 16px; color: #888;'>LIVE</span></h1>", unsafe_allow_html=True)
    
    render_chart(selected_asset, chart_data)

with col_order:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Place Order")
    
    with st.form("order_terminal"):
        qty = st.number_input("Quantity (Lots)", min_value=1, value=1)
        
        # Toggle Buttons styling using radio
        action = st.radio("Action", ["BUY", "SELL"], horizontal=True)
        
        lot = ASSETS[selected_asset]['lot']
        val = inr_price * qty * lot
        
        st.divider()
        st.markdown(f"**Margin Req:** <br><span style='font-size: 18px'>₹{val:,.0f}</span>", unsafe_allow_html=True)
        st.caption(f"Brokerage: ₹{BROKERAGE_PER_ORDER}")
        
        if st.form_submit_button("COMPLETE ORDER"):
            cost = val + BROKERAGE_PER_ORDER if action == "BUY" else val - BROKERAGE_PER_ORDER
            
            if action == "BUY" and st.session_state.balance < cost:
                st.error("Insufficient Funds")
            else:
                new_bal = st.session_state.balance - cost if action == "BUY" else st.session_state.balance + cost
                update_user_balance(st.session_state.user, new_bal)
                log_trade({
                    'Time': time.strftime("%Y-%m-%d %H:%M:%S"), 'User': st.session_state.user,
                    'Symbol': selected_asset, 'Action': action, 'Qty': qty,
                    'Price': inr_price, 'Value': val, 'Fees': BROKERAGE_PER_ORDER
                })
                update_portfolio(st.session_state.user, selected_asset, qty, inr_price, action)
                st.session_state.balance = new_bal
                st.success("Executed")
                time.sleep(1)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# --- PORTFOLIO SECTION (BOTTOM) ---
st.markdown("### 💼 Positions")
try:
    ws = connect_db().worksheet("Portfolio")
    df_port = pd.DataFrame(ws.get_all_records())
except: df_port = pd.DataFrame()

if not df_port.empty:
    my_port = df_port[df_port['User'] == st.session_state.user]
    if not my_port.empty:
        # Create a nice dark table
        rows = []
        total_pnl = 0.0
        
        for idx, row in my_port.iterrows():
            sym = row['Symbol']
            qty = row['Qty']
            avg = row['Avg_Price']
            
            curr_usd, _ = get_market_data(sym, "1d", "1h") # Fast check
            curr_inr = curr_usd * 84.0
            
            pnl = (curr_inr - avg) * qty * ASSETS[sym]['lot']
            total_pnl += pnl
            
            pnl_html = f"<span class='text-green'>+{pnl:,.2f}</span>" if pnl > 0 else f"<span class='text-red'>{pnl:,.2f}</span>"
            
            rows.append([sym, qty, f"₹{avg:,.2f}", f"₹{curr_inr:,.2f}", pnl_html])
            
        # Display as custom HTML table for look
        table_html = "<table style='width:100%; text-align: left;'>"
        table_html += "<tr style='color:#888;'><th>Instrument</th><th>Qty</th><th>Avg.</th><th>LTP</th><th>P&L</th></tr>"
        for r in rows:
            table_html += f"<tr style='border-bottom: 1px solid #333;'><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td></tr>"
        table_html += "</table>"
        
        st.markdown(table_html, unsafe_allow_html=True)
        
        # Total P&L Footer
        st.markdown(f"""
            <div style="margin-top: 20px; padding: 15px; background: #161616; border-left: 5px solid {'#2ecc71' if total_pnl >= 0 else '#e74c3c'};">
                <span style="font-size: 14px; color: #aaa;">TOTAL P&L</span><br>
                <span style="font-size: 24px; font-weight: bold; color: {'#2ecc71' if total_pnl >= 0 else '#e74c3c'};">₹{total_pnl:,.2f}</span>
            </div>
        """, unsafe_allow_html=True)
        
    else: st.info("No open positions")
else: st.info("No open positions")
