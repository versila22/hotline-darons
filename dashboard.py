import streamlit as st
import sqlite3
import pandas as pd
import json
from pathlib import Path
import os

# Set page config
st.set_page_config(
    page_title="Hotline Darons L2 Dashboard",
    page_icon="🚨",
    layout="wide"
)

# Basic Authentication using environment variable instead of secrets for simplicity in this setup
def check_password():
    """Returns `True` if the user had the correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        expected_password = os.environ.get("STREAMLIT_PASSWORD", "admin123")
        if st.session_state["password"] == expected_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True

if not check_password():
    st.stop()  # Do not continue if check_password is False

# --- Main Dashboard ---

st.title("🚨 Hotline Darons - L2 Escalation Dashboard")
st.markdown("Interface de suivi Niveau 2 pour consulter l'historique des escalades.")

# Config DB path
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).resolve().parent / "data" / "hotline_darons.db"))

def load_data():
    if not os.path.exists(DB_PATH):
        st.warning(f"Database not found at {DB_PATH}")
        return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        # Ensure table exists in case it's loaded before bot creates it
        conn.execute('''
            CREATE TABLE IF NOT EXISTS escalations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                summary TEXT NOT NULL,
                has_photo BOOLEAN NOT NULL DEFAULT 0
            )
        ''')
        
        query = "SELECT * FROM escalations ORDER BY id DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Convert timestamp to a more readable format if dataframe is not empty
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
            df['has_photo'] = df['has_photo'].apply(lambda x: '📸 Oui' if x else '❌ Non')
            
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# Refresh button
col1, col2 = st.columns([1, 10])
with col1:
    if st.button("🔄 Refresh"):
        st.rerun()

df = load_data()

if df.empty:
    st.info("Aucune escalade enregistrée pour le moment. (No escalations recorded yet).")
else:
    # Key metrics
    st.markdown("### Statistiques")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Escalades", len(df))
    
    # Calculate escalations in last 24h
    if not df.empty:
        df['dt'] = pd.to_datetime(df['timestamp'])
        last_24h = len(df[df['dt'] > (pd.Timestamp.now() - pd.Timedelta(days=1))])
        m2.metric("Escalades (24h)", last_24h)
        
        photo_count = len(df[df['has_photo'] == '📸 Oui'])
        m3.metric("Escalades avec Photo", photo_count)
        
        # Drop temp dt column for display
        df = df.drop(columns=['dt'])
    
    st.markdown("### Historique")
    st.dataframe(
        df,
        column_config={
            "id": "ID",
            "timestamp": "Date & Heure",
            "user_id": "User ID",
            "user_name": "Utilisateur",
            "summary": "Résumé de l'escalade",
            "has_photo": "Photo jointe ?"
        },
        hide_index=True,
        use_container_width=True
    )
