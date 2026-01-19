import streamlit as st
import requests
import sqlite3
import threading
from datetime import date
from datetime import datetime

#telegram config
TELEGRAM_BOT_TOKEN = "8484384102:AAESdSCdUZUaxhfpQp2YSpZhofpwAFE_qhI"
TELEGRAM_CHAT_ID = "1676807915"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram error:", e)

def send_telegram_message_async(text):
    def task(msg):
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
        except Exception as e:
            print("Telegram error:", e)

    threading.Thread(target=task, args=(text,), daemon=True).start()

# ---------- CONFIG ----------
st.set_page_config(
    page_title="Ethan Kick Counter",
    page_icon="👶",
    layout="centered"
)

DB_PATH = "kicks.db"
PIN_CODE = "0802"

# ---------- DATABASE ----------
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
    c.execute(
        "SELECT count FROM kicks WHERE kick_date=?",
        (str(date.today()),)
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def save_kick(count):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO kicks (kick_date, count)
        VALUES (?, ?)
        ON CONFLICT(kick_date)
        DO UPDATE SET count=excluded.count
    """, (str(date.today()), count))
    conn.commit()
    conn.close()
    
def log_kick_event():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO kick_events (kick_time) VALUES (?)",
        (datetime.now().isoformat(),)
    )
    conn.commit()
    conn.close()

# ---------- INIT ----------
init_db()

# ---------- SESSION ----------
if "logged_in" not in st.session_state:
    last_login = get_last_login_date()
    st.session_state.logged_in = (last_login == str(date.today()))

if "pin_input" not in st.session_state:
    st.session_state.pin_input = ""



# ---------- PIN LOGIN ----------
if not st.session_state.logged_in:
    st.title("👶 Ethan Kick Counter")
    st.subheader("Enter PIN")

    st.markdown(
        f"""
        <div style="text-align:center; font-size:36px; letter-spacing:10px;">
            {"•" * len(st.session_state.pin_input)}
        </div>
        """,
        unsafe_allow_html=True
    )

    keypad = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["⌫", "0", "✓"]
    ]

    for row in keypad:
        cols = st.columns(3)
        for i, key in enumerate(row):
            if cols[i].button(key, use_container_width=True):
                if key == "⌫":
                    st.session_state.pin_input = st.session_state.pin_input[:-1]
                elif key == "✓":
                    if st.session_state.pin_input == PIN_CODE:
                        st.session_state.logged_in = True
                        save_login_date(str(date.today()))
                        st.session_state.pin_input = ""
                        st.rerun()
                    else:
                        st.session_state.pin_input = ""
                        st.error("Wrong PIN")
                else:
                    if len(st.session_state.pin_input) < 4:
                        st.session_state.pin_input += key
                st.rerun()

    st.stop()

# ---------- MAIN APP ----------
page = st.sidebar.radio("Page", ["Home", "Analytics"])

if page == "Home":
    today_count = get_today_kicks()

    st.title("👶 Ethan Kick Counter")
    st.caption(f"{date.today()}")

    st.markdown(
        f"""
        <div style="text-align:center; font-size:56px; font-weight:bold;">
            {today_count}
        </div>
        <div style="text-align:center; font-size:18px;">
            kicks today
        </div>
        """,
        unsafe_allow_html=True
    )

    st.write("")

    if st.button("➕ ADD KICK", use_container_width=True):
        now = datetime.now()
        today_count += 1

        save_kick(today_count)
        log_kick_event()

        send_telegram_message_async(
            f"👶 Kick logged!\n"
            f"Time: {now.strftime('%H:%M')}\n"
            f"Total today: {today_count}"
        )

        st.rerun()
        

    with st.expander("⚙️ Settings"):
        if st.button("🔄 Reset Today"):
            save_kick(0)
            st.rerun()

    st.caption("PIN login once per day • Mobile friendly")
    
if page == "Analytics":
    import pandas as pd
    import matplotlib.pyplot as plt
    from datetime import datetime, time

    st.title("📊 Analytics")

    conn = get_connection()
    df = pd.read_sql(
        "SELECT kick_time FROM kick_events",
        conn,
        parse_dates=["kick_time"]
    )
    conn.close()

    if df.empty:
        st.info("Not enough data yet.")
        st.stop()

    df["date"] = df["kick_time"].dt.date
    df["time"] = df["kick_time"].dt.time

    # ---------- 1️⃣ TABLE: kicks today ----------
    st.subheader("Kicks Today (Time)")
    today = date.today()
    today_df = df[df["date"] == today]

    if today_df.empty:
        st.write("No kicks logged today.")
        
    if not today_df.empty:
        table_df = today_df.copy()
        table_df["Time (HH:MM)"] = table_df["kick_time"].dt.strftime("%H:%M")
        table_df.insert(0, "#", range(1, len(table_df)+1))  # Add numbering starting at 1
        st.table(table_df[["#", "Time (HH:MM)"]])

    # ---------- 2️⃣ AVG INTERVAL PLOT ----------
    st.subheader("Average Kicking Interval")

    days = st.selectbox("Lookback window (days)", [10, 20, 30])

    cutoff = date.today().toordinal() - days
    recent = df[df["date"].apply(lambda d: d.toordinal() >= cutoff)]

    interval_data = []

    for d, group in recent.groupby("date"):
        if len(group) < 2:
            continue
        times = group["kick_time"].sort_values()
        intervals = times.diff().dropna().dt.total_seconds() / 3600
        interval_data.append({
            "date": d,
            "avg_interval": intervals.mean()
        })

    interval_df = pd.DataFrame(interval_data)

    if interval_df.empty:
        st.write("Not enough data to calculate intervals.")
    else:
        fig, ax = plt.subplots()
        ax.plot(
            interval_df["date"],
            interval_df["avg_interval"],
            marker="o"
        )
        ax.set_ylabel("Hours per kick")
        ax.set_xlabel("Date")
        ax.set_title("Average Kicking Interval")
        plt.xticks(rotation=45)
        st.pyplot(fig)

    # ---------- 3️⃣ TIME DISTRIBUTION PLOT ----------
    st.subheader("Kick Distribution (9am–7pm)")

    df["hour"] = (
        df["kick_time"].dt.hour +
        df["kick_time"].dt.minute / 60
    )

    hist = df[(df["hour"] >= 9) & (df["hour"] <= 19)]
    today_hist = hist[hist["date"] == today]

    fig, ax = plt.subplots()

    ax.scatter(
        hist["hour"],
        hist["date"],
        alpha=0.3,
        label="Historical"
    )

    if not today_hist.empty:
        ax.scatter(
            today_hist["hour"],
            today_hist["date"],
            label="Today"
        )

    ax.set_xlim(8, 20)
    ax.set_xlabel("Time of day (hr)")
    ax.set_ylabel("Date")
    ax.set_title("Kick Timing Pattern (9am–7pm)")
    ax.legend()

    st.pyplot(fig)

