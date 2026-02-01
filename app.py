import streamlit as st
import requests
import threading
import pytz
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, time
from matplotlib.backends.backend_pdf import PdfPages
from supabase import create_client

# ---------- TIMEZONE ----------
MALAYSIA_TZ = pytz.timezone("Asia/Kuala_Lumpur")
UTC = pytz.UTC

# ---------- SUPABASE ----------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- SECURITY ----------
PIN_CODE = st.secrets["PIN_CODE"]

# ---------- TELEGRAM ----------
TELEGRAM_BOT_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_IDS = [
    cid.strip()
    for cid in st.secrets["TELEGRAM_CHAT_IDS"].split(",")
]

def send_telegram_message_async(text):
    def task(msg):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        for chat_id in TELEGRAM_CHAT_IDS:
            try:
                requests.post(
                    url,
                    json={"chat_id": chat_id, "text": msg},
                    timeout=5
                )
            except Exception as e:
                print("Telegram error:", e)
    threading.Thread(target=task, args=(text,), daemon=True).start()

# ---------- DATABASE HELPERS ----------
def get_last_login_date():
    res = supabase.table("login").select("last_login_date").eq("id", 1).execute()
    return res.data[0]["last_login_date"] if res.data else None

def save_login_date(login_date):
    supabase.table("login").upsert({
        "id": 1,
        "last_login_date": login_date
    }).execute()

def get_today_kicks():
    today = datetime.now(MALAYSIA_TZ).date().isoformat()
    res = supabase.table("kicks").select("count").eq("kick_date", today).execute()
    return res.data[0]["count"] if res.data else 0

def save_kick(count):
    today = datetime.now(MALAYSIA_TZ).date().isoformat()
    supabase.table("kicks").upsert({
        "kick_date": today,
        "count": count
    }).execute()

def log_kick_event():
    supabase.table("kick_events").insert({
        "kick_time": datetime.utcnow().isoformat()
    }).execute()

def reset_today():
    today = datetime.now(MALAYSIA_TZ).date().isoformat()
    supabase.table("kicks").delete().eq("kick_date", today).execute()

    start = datetime.combine(datetime.now(MALAYSIA_TZ).date(), time.min).astimezone(UTC).isoformat()
    end = datetime.combine(datetime.now(MALAYSIA_TZ).date(), time.max).astimezone(UTC).isoformat()

    supabase.table("kick_events") \
        .delete() \
        .gte("kick_time", start) \
        .lte("kick_time", end) \
        .execute()

# ---------- PDF ----------
def generate_pdf(today_df, interval_df, hist_df, today_hist, today):
    pdf_path = "ethan_kick_report.pdf"

    with PdfPages(pdf_path) as pdf:

        # Title
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        ax.axis("off")
        ax.text(0.5, 0.7, "Ethan Kick Report", ha="center", fontsize=24)
        ax.text(0.5, 0.6, f"Generated on: {today}", ha="center", fontsize=14)
        pdf.savefig(fig)
        plt.close(fig)

        # Table
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        ax.axis("off")
        ax.set_title("Kicks Today", fontsize=16)
        if today_df.empty:
            ax.text(0.5, 0.5, "No kicks logged today.", ha="center")
        else:
            table_df = today_df.copy()
            table_df["Time"] = table_df["kick_time"].dt.strftime("%H:%M")
            ax.table(
                cellText=table_df[["Time"]].values,
                colLabels=["Time"],
                loc="center",
                cellLoc="center"
            )
        pdf.savefig(fig)
        plt.close(fig)

        # Interval plot
        if not interval_df.empty:
            fig, ax = plt.subplots()
            ax.plot(interval_df["date"], interval_df["avg_interval"], marker="o")
            ax.set_title("Average Kicking Interval")
            ax.set_ylabel("Hours per kick")
            ax.set_xlabel("Date")
            plt.xticks(rotation=45)
            pdf.savefig(fig)
            plt.close(fig)

        # Distribution
        fig, ax = plt.subplots()
        ax.scatter(hist_df["hour"], hist_df["date"], alpha=0.3, label="Historical")
        if not today_hist.empty:
            ax.scatter(today_hist["hour"], today_hist["date"], label="Today")
        ax.set_xlim(8, 20)
        ax.set_title("Kick Timing Pattern (9am–7pm)")
        ax.legend()
        pdf.savefig(fig)
        plt.close(fig)

    return pdf_path

# ---------- APP ----------
st.set_page_config(page_title="Ethan Kick Counter", page_icon="👶")

# ---------- SESSION ----------
if "logged_in" not in st.session_state:
    last_login = get_last_login_date()
    st.session_state.logged_in = (last_login == str(datetime.now(MALAYSIA_TZ).date()))
if "pin_input" not in st.session_state:
    st.session_state.pin_input = ""

# ---------- LOGIN ----------
if not st.session_state.logged_in:
    st.title("👶 Ethan Kick Counter")
    st.subheader("Enter PIN")

    keypad = [["1","2","3"], ["4","5","6"], ["7","8","9"], ["⌫","0","✓"]]
    for row in keypad:
        cols = st.columns(3)
        for i, key in enumerate(row):
            if cols[i].button(key, use_container_width=True):
                if key == "⌫":
                    st.session_state.pin_input = st.session_state.pin_input[:-1]
                elif key == "✓":
                    if st.session_state.pin_input == PIN_CODE:
                        st.session_state.logged_in = True
                        save_login_date(str(datetime.now(MALAYSIA_TZ).date()))
                        st.session_state.pin_input = ""
                        st.rerun()
                    else:
                        st.session_state.pin_input = ""
                        st.error("Wrong PIN")
                else:
                    st.session_state.pin_input += key
                st.rerun()
    st.stop()

# ---------- MAIN ----------
page = st.sidebar.radio("Page", ["Home", "Analytics"])

if page == "Home":
    today_count = get_today_kicks()
    st.title("👶 Ethan Kick Counter")
    st.markdown(f"<h1 style='text-align:center'>{today_count}</h1>", unsafe_allow_html=True)

    if st.button("➕ ADD KICK", use_container_width=True):
        today_count += 1
        save_kick(today_count)
        log_kick_event()
        send_telegram_message_async(
            f"👶 Kick logged!\nTime: {datetime.now(MALAYSIA_TZ).strftime('%H:%M')}\nTotal today: {today_count}"
        )
        st.rerun()

    if st.button("🔄 Reset Today"):
        reset_today()
        st.rerun()

elif page == "Analytics":
    st.title("📊 Analytics")

    res = supabase.table("kick_events").select("kick_time").execute()
    df = pd.DataFrame(res.data)

    if df.empty:
        st.info("Not enough data yet.")
        st.stop()

    df["kick_time"] = pd.to_datetime(df["kick_time"], utc=True).dt.tz_convert(MALAYSIA_TZ)
    df["date"] = df["kick_time"].dt.date
    df["hour"] = df["kick_time"].dt.hour + df["kick_time"].dt.minute / 60

    # ---- Table: today ----
    st.subheader("Kicks Today (Time)")
    today = datetime.now(MALAYSIA_TZ).date()
    today_df = df[df["date"] == today]
    if today_df.empty:
        st.write("No kicks logged today.")
    else:
        table_df = today_df.copy()
        table_df["Time"] = table_df["kick_time"].dt.strftime("%H:%M")
        table_df.insert(0, "#", range(1, len(table_df) + 1))
        st.table(table_df[["#", "Time"]])

    # ---- Interval plot ----
    st.subheader("Average Kicking Interval")
    days = st.selectbox("Lookback window (days)", [10, 20, 30])
    cutoff = today.toordinal() - days
    recent = df[df["date"].apply(lambda d: d.toordinal() >= cutoff)]

    interval_data = []
    for d, g in recent.groupby("date"):
        if len(g) < 2:
            continue
        intervals = g["kick_time"].sort_values().diff().dropna().dt.total_seconds() / 3600
        interval_data.append({"date": d, "avg_interval": intervals.mean()})

    interval_df = pd.DataFrame(interval_data)
    if not interval_df.empty:
        fig, ax = plt.subplots()
        ax.plot(interval_df["date"], interval_df["avg_interval"], marker="o")
        ax.set_ylabel("Hours per kick")
        ax.set_xlabel("Date")
        plt.xticks(rotation=45)
        st.pyplot(fig)

    # ---- Distribution plot ----
    st.subheader("Kick Distribution (9am–7pm)")
    hist = df[(df["hour"] >= 9) & (df["hour"] <= 19)]
    today_hist = hist[hist["date"] == today]

    fig, ax = plt.subplots()
    ax.scatter(hist["hour"], hist["date"], alpha=0.3, label="Historical")
    if not today_hist.empty:
        ax.scatter(today_hist["hour"], today_hist["date"], label="Today")
    ax.set_xlim(8, 20)
    ax.legend()
    st.pyplot(fig)

    # ---- PDF ----
    st.divider()
    if st.button("Generate PDF Report"):
        pdf = generate_pdf(today_df, interval_df, hist, today_hist, today)
        with open(pdf, "rb") as f:
            st.download_button(
                "⬇️ Download PDF",
                f,
                file_name="ethan_kick_report.pdf",
                mime="application/pdf"
            )
