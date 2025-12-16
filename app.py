import streamlit as st
import pandas as pd
import yfinance as yf
import time
import random
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
st.set_page_config(page_title="ProTrade Live", layout="wide", page_icon="⚡")
BROKERAGE_PER_ORDER = 500.0 

# --- CONNECT TO GOOGLE SHEETS ---
def connect_db():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        # !!! CHANGE THIS TO YOUR EXACT SHEET NAME !!!
        return client.open("My Trade DB")
    except Exception as e:
        st.error(f"Connection Error: {e}")
        st.stop()

# --- DATABASE FUNCTIONS ---
def get_users():
    try:
        return pd.DataFrame(connect_db().worksheet("Users").get_all_records())
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
        new_qty = curr_qty + qty if action == "BUY" else curr_qty - qty
        
        if new_qty <= 0: ws.delete_rows(int(row_idx))
        else: ws.update_cell(int(row_idx), 4, int(new_qty)) # Col 4 is Qty
    elif action == "BUY":
        # New Position: Key, User, Symbol, Qty, AvgPrice
        ws.append_row([key, user, symbol, qty, price])

# --- 🔥 LIVE PRICE SIMULATION ---
def get_live_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if data.empty: return 0.0
        base = data['Close'].iloc[-1]
        # Add fake volatility (±0.05%) to make it look alive
        noise = base * 0.0005 
        live_price = base + random.uniform(-noise, noise)
        return round(live_price, 2)
    except: return 0.0

# --- APP START ---
if 'user' not in st.session_state:
    st.title("🔐 ProTrade Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        df = get_users()
        if not df.empty and u in df['Username'].values:
            user_row = df[df['Username'] == u].iloc[0]
            # Convert to string to avoid format errors
            if str(user_row['Password']) == str(p) and str(user_row['Active']).upper() == 'TRUE':
                st.session_state.user = u
                st.session_state.role = user_row['Role']
                st.session_state.balance = float(user_row['Balance'])
                st.rerun()
            else: st.error("Wrong Password or Account Inactive")
        else: st.error("User Not Found")
    st.stop()

# --- SIDEBAR MENU ---
st.sidebar.title(f"👤 {st.session_state.user}")
if st.sidebar.button("Logout"):
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.rerun()

# --- ADMIN PANEL ---
if st.session_state.role == 'MASTER':
    st.title("👑 Master Admin Panel")
    tab1, tab2 = st.tabs(["👥 User Database", "📜 Trade Logs"])
    with tab1:
        st.dataframe(get_users())
        st.info("💡 To add money or users, edit the Google Sheet directly.")
    with tab2:
        if st.button("Refresh Logs"):
            st.dataframe(pd.DataFrame(connect_db().worksheet("Orders").get_all_records()))

# --- TRADING TERMINAL ---
else:
    st.title("📈 ProTrade Terminal")
    
    # Refresh logic to simulate ticks
    if st.button("🔄 Refresh Market"):
        st.rerun()

    # Metrics
    col1, col2 = st.columns(2)
    col1.metric("💰 Wallet Balance", f"₹{st.session_state.balance:,.2f}")
    
    # Market Watch
    commodities = {"Gold": "GC=F", "Crude Oil": "CL=F", "Silver": "SI=F"}
    selected = st.selectbox("Select Asset", list(commodities.keys()))
    
    # Price Conversion
    usd_price = get_live_price(commodities[selected])
    inr_price = usd_price * 83.50 # Approx USD-INR rate
    
    st.metric(label=f"⚡ {selected} LIVE", value=f"₹{inr_price:,.2f}")
    
    # Order Form
    c1, c2 = st.columns(2)
    qty = c1.number_input("Lots", 1, 100)
    action = c2.radio("Action", ["BUY", "SELL"], horizontal=True)
    
    trade_val = inr_price * qty
    total_cost = trade_val + BROKERAGE_PER_ORDER if action == "BUY" else trade_val - BROKERAGE_PER_ORDER
    
    st.info(f"Price: ₹{trade_val:,.0f} | Brokerage: ₹500 | **Net: ₹{total_cost:,.0f}**")

    if st.button("⚡ EXECUTE TRADE"):
        if action == "BUY" and st.session_state.balance < total_cost:
            st.error("Insufficient Funds!")
        else:
            new_bal = st.session_state.balance - total_cost if action == "BUY" else st.session_state.balance + total_cost
            
            # 1. Update Cloud Balance
            update_user_balance(st.session_state.user, new_bal)
            
            # 2. Log Trade
            log_trade({
                'Time': time.strftime("%Y-%m-%d %H:%M:%S"),
                'User': st.session_state.user,
                'Symbol': selected,
                'Action': action,
                'Qty': qty,
                'Price': inr_price,
                'Value': trade_val,
                'Brokerage': BROKERAGE_PER_ORDER
            })
            
            # 3. Update Portfolio
            update_portfolio(st.session_state.user, selected, qty, inr_price, action)
            
            st.session_state.balance = new_bal
            st.success("✅ Trade Successful!")
            time.sleep(1)
            st.rerun()
      
