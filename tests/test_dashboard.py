import sqlite3
import tempfile
import os
from datetime import datetime, timezone

from bot.escalation import _save_escalation_to_db
import bot.config as config

def test_save_escalation_to_db():
    # Setup temporary database
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_db = f.name
    
    # Temporarily override DB_PATH
    old_db_path = config.DB_PATH
    config.DB_PATH = temp_db
    
    try:
        user_info = {
            "id": 12345,
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser"
        }
        summary = "Test escalation summary"
        
        # Call function
        _save_escalation_to_db(user_info, summary, True)
        
        # Verify db contents
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, user_name, summary, has_photo FROM escalations")
        row = cursor.fetchone()
        
        assert row is not None
        assert row[0] == 12345
        assert "Test User" in row[1]
        assert row[2] == summary
        assert row[3] == 1 # True is stored as 1
        
        conn.close()
    finally:
        config.DB_PATH = old_db_path
        os.remove(temp_db)
