import streamlit as st
import os
import requests
import sqlite3
import threading
import pytz
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date, time, timedelta
from matplotlib.backends.backend_pdf import PdfPages

# ---------- TIMEZONE ----------
MALAYSIA_TZ = pytz.timezone("Asia/Kuala_Lumpur")
UTC = pytz.UTC

# ---------- DATABASE ----------
DB_PATH = "/mount/src/kicks.db"
PIN_CODE = st.secrets["PIN_CODE"]

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS kicks (
        kick_date TEXT PRIMARY KEY,
        count INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS kick_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kick_time TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS login (
        id INTEGER PRIMARY KEY,
        last_login_date TEXT
    )
    """)

    conn.commit()
    conn.close()

def get_last_login_date():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT last_login_date FROM login WHERE id=1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def save_login_date(login_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO login (id, last_login_date)
        VALUES (1, ?)
        ON CONFLICT(id)
        DO UPDATE SET last_login_date=excluded.last_login_date
    """, (login_date,))
    conn.commit()
    conn.close()

def get_today_kicks():
    conn = get_connection()
    c = conn.cursor()
    today_str = datetime.now(MALAYSIA_TZ).date().isoformat()
    c.execute("SELECT count FROM kicks WHERE kick_date=?", (today_str,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def save_kick(count):
    conn = get_connection()
    c = conn.cursor()
    today_str = datetime.now(MALAYSIA_TZ).date().isoformat()
    c.execute("""
        INSERT INTO kicks (kick_date, count)
        VALUES (?, ?)
        ON CONFLICT(kick_date)
        DO UPDATE SET count=excluded.count
    """, (today_str, count))
    conn.commit()
    conn.close()

def log_kick_event():
    conn = get_connection()
    c = conn.cursor()
    now_utc = datetime.utcnow().replace(tzinfo=UTC)
    c.execute("INSERT INTO kick_events (kick_time) VALUES (?)", (now_utc.isoformat(),))
    conn.commit()
    conn.close()

def reset_today():
    conn = get_connection()
    c = conn.cursor()
    today_str = datetime.now(MALAYSIA_TZ).date().isoformat()
    c.execute("DELETE FROM kicks WHERE kick_date=?", (today_str,))
    # Delete today's events (stored in UTC)
    today_start_utc = datetime.combine(datetime.now(MALAYSIA_TZ).date(), time.min).astimezone(UTC)
    today_end_utc = datetime.combine(datetime.now(MALAYSIA_TZ).date(), time.max).astimezone(UTC)
    c.execute("DELETE FROM kick_events WHERE kick_time BETWEEN ? AND ?", 
              (today_start_utc.isoformat(), today_end_utc.isoformat()))
    conn.commit()
    conn.close()

def generate_pdf(today_df, interval_df, hist_df, today_hist, today):
    pdf_path = "/mount/src/ethan_kick_report.pdf"

    with PdfPages(pdf_path) as pdf:

        # ---------- PAGE 1: TITLE ----------
        fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4
        ax.axis("off")
        ax.text(0.5, 0.7, "Ethan Kick Report", ha="center", fontsize=24)
        ax.text(0.5, 0.6, f"Generated on: {today}", ha="center", fontsize=14)
        ax.text(0.5, 0.5, "Tracking baby kick patterns", ha="center", fontsize=12)
        pdf.savefig(fig)
        plt.close(fig)

        # ---------- PAGE 2: TABLE ----------
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        ax.axis("off")
        ax.set_title("Kicks Today", fontsize=16, pad=20)

        if today_df.empty:
            ax.text(0.5, 0.5, "No kicks logged today.", ha="center")
        else:
            table_df = today_df.copy()
            table_df["Time"] = table_df["kick_time"].dt.strftime("%H:%M")
            table_df = table_df[["Time"]]

            table = ax.table(
                cellText=table_df.values,
                colLabels=table_df.columns,
                loc="center",
                cellLoc="center"
            )
            table.scale(1, 1.5)

        pdf.savefig(fig)
        plt.close(fig)

        # ---------- PAGE 3: INTERVAL PLOT ----------
        if not interval_df.empty:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(interval_df["date"], interval_df["avg_interval"], marker="o")
            ax.set_ylabel("Hours per kick")
            ax.set_xlabel("Date")
            ax.set_title("Average Kicking Interval")
            plt.xticks(rotation=45)
            pdf.savefig(fig)
            plt.close(fig)

        # ---------- PAGE 4: DISTRIBUTION ----------
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.scatter(hist_df["hour"], hist_df["date"], alpha=0.3, label="Historical")
        if not today_hist.empty:
            ax.scatter(today_hist["hour"], today_hist["date"], label="Today")
        ax.set_xlim(8, 20)
        ax.set_xlabel("Time of day (hr)")
        ax.set_ylabel("Date")
        ax.set_title("Kick Timing Pattern (9am–7pm)")
        ax.legend()
        pdf.savefig(fig)
        plt.close(fig)

    return pdf_path


# ---------- TELEGRAM ----------
TELEGRAM_BOT_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

def send_telegram_message_async(text):
    def task(msg):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
        except Exception as e:
            print("Telegram error:", e)
    threading.Thread(target=task, args=(text,), daemon=True).start()

# ---------- CONFIG ----------
st.set_page_config(page_title="Ethan Kick Counter", page_icon="👶", layout="centered")
init_db()

st.sidebar.markdown("### 🔍 DB Check")
st.sidebar.write("DB_PATH:", DB_PATH)
st.sidebar.write("Exists:", os.path.exists(DB_PATH))
if os.path.exists(DB_PATH):
    st.sidebar.write("Size:", os.path.getsize(DB_PATH))

# ---------- SESSION ----------
if "logged_in" not in st.session_state:
    last_login = get_last_login_date()
    st.session_state.logged_in = (last_login == str(datetime.now(MALAYSIA_TZ).date()))
if "pin_input" not in st.session_state:
    st.session_state.pin_input = ""

# ---------- PIN LOGIN ----------
if not st.session_state.logged_in:
    st.title("👶 Ethan Kick Counter")
    st.subheader("Enter PIN")
    st.markdown(f"<div style='text-align:center; font-size:36px; letter-spacing:10px;'>{'•'*len(st.session_state.pin_input)}</div>", unsafe_allow_html=True)

    keypad = [["1","2","3"], ["4","5","6"], ["7","8","9"], ["⌫","0","✓"]]
    for row in keypad:
        cols = st.columns(3)
        for i, key in enumerate(row):
            if cols[i].button(key, use_container_width=True):
                if key=="⌫":
                    st.session_state.pin_input = st.session_state.pin_input[:-1]
                elif key=="✓":
                    if st.session_state.pin_input == PIN_CODE:
                        st.session_state.logged_in = True
                        save_login_date(str(datetime.now(MALAYSIA_TZ).date()))
                        st.session_state.pin_input = ""
                        st.rerun()
                    else:
                        st.session_state.pin_input = ""
                        st.error("Wrong PIN")
                else:
                    if len(st.session_state.pin_input)<4:
                        st.session_state.pin_input += key
                st.rerun()
    st.stop()

# ---------- MAIN APP ----------
page = st.sidebar.radio("Page", ["Home", "Analytics"])

if page=="Home":
    today_count = get_today_kicks()
    st.title("👶 Ethan Kick Counter")
    st.caption(f"{datetime.now(MALAYSIA_TZ).date()}")

    st.markdown(f"<div style='text-align:center; font-size:56px; font-weight:bold;'>{today_count}</div>"
                "<div style='text-align:center; font-size:18px;'>kicks today</div>", unsafe_allow_html=True)

    if st.button("➕ ADD KICK", use_container_width=True):
        now = datetime.now(MALAYSIA_TZ)
        today_count += 1
        save_kick(today_count)
        log_kick_event()
        send_telegram_message_async(f"👶 Kick logged!\nTime: {now.strftime('%H:%M')}\nTotal today: {today_count}")
        st.rerun()

    with st.expander("⚙️ Settings"):
        if st.button("🔄 Reset Today"):
            reset_today()
            st.success("Today's kicks reset!")
            st.rerun()
    st.caption("PIN login once per day • Mobile friendly")
    
elif page=="Analytics":
    st.title("📊 Analytics")
    conn = get_connection()
    df = pd.read_sql("SELECT kick_time FROM kick_events", conn, parse_dates=["kick_time"])
    st.write("Total kick events in DB:", len(df))
    st.write(df.tail(5))
    conn.close()

    if df.empty:
        st.info("Not enough data yet.")
        st.stop()

    # Convert UTC to Malaysia time
    df["kick_time"] = pd.to_datetime(df["kick_time"])

    # If tz-naive, localize to UTC first
    if df["kick_time"].dt.tz is None:
        df["kick_time"] = df["kick_time"].dt.tz_localize('UTC')

    # Convert to Malaysia timezone
    df["kick_time"] = df["kick_time"].dt.tz_convert(MALAYSIA_TZ)

    df["date"] = df["kick_time"].dt.date
    df["time"] = df["kick_time"].dt.time

    # ---------- Table: Kicks Today ----------
    st.subheader("Kicks Today (Time)")
    today = datetime.now(MALAYSIA_TZ).date()
    today_df = df[df["date"]==today]
    if today_df.empty:
        st.write("No kicks logged today.")
    else:
        table_df = today_df.copy()
        table_df["Time (HH:MM)"] = table_df["kick_time"].dt.strftime("%H:%M")
        table_df.insert(0, "#", range(1, len(table_df)+1))
        st.table(table_df[["#", "Time (HH:MM)"]])

    # ---------- Average Interval Plot ----------
    st.subheader("Average Kicking Interval")
    days = st.selectbox("Lookback window (days)", [10,20,30])
    cutoff = today.toordinal() - days
    recent = df[df["date"].apply(lambda d: d.toordinal() >= cutoff)]
    interval_data = []
    for d, group in recent.groupby("date"):
        if len(group)<2:
            continue
        times = group["kick_time"].sort_values()
        intervals = times.diff().dropna().dt.total_seconds()/3600
        interval_data.append({"date":d, "avg_interval":intervals.mean()})
    interval_df = pd.DataFrame(interval_data)
    if interval_df.empty:
        st.write("Not enough data to calculate intervals.")
    else:
        fig, ax = plt.subplots()
        ax.plot(interval_df["date"], interval_df["avg_interval"], marker="o")
        ax.set_ylabel("Hours per kick")
        ax.set_xlabel("Date")
        ax.set_title("Average Kicking Interval")
        plt.xticks(rotation=45)
        st.pyplot(fig)

    # ---------- Kick Distribution Plot ----------
    st.subheader("Kick Distribution (9am–7pm)")
    df["hour"] = df["kick_time"].dt.hour + df["kick_time"].dt.minute/60
    hist = df[(df["hour"]>=9)&(df["hour"]<=19)]
    today_hist = hist[hist["date"]==today]

    fig, ax = plt.subplots()
    ax.scatter(hist["hour"], hist["date"], alpha=0.3, label="Historical")
    if not today_hist.empty:
        ax.scatter(today_hist["hour"], today_hist["date"], label="Today")
    ax.set_xlim(8,20)
    ax.set_xlabel("Time of day (hr)")
    ax.set_ylabel("Date")
    ax.set_title("Kick Timing Pattern (9am–7pm)")
    ax.legend()
    st.pyplot(fig)

    st.divider()
    st.subheader("📄 Export Report")

    if st.button("Generate PDF Report"):
        pdf_path = generate_pdf(today_df, interval_df, hist, today_hist, today)
        with open(pdf_path, "rb") as f:
            st.download_button(
                label="⬇️ Download PDF",
                data=f,
                file_name="ethan_kick_report.pdf",
                mime="application/pdf"
            )




