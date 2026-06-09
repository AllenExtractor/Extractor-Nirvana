# utils/cleanup.py
import os
import time

def cleanup_old_files(directory=".", max_age_minutes=20):
    """Delete ANY file older than given time in minutes."""
    now = time.time()
    for root, dirs, files in os.walk(directory):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                file_age = now - os.path.getmtime(file_path)
                if file_age > max_age_minutes * 60:
                    os.remove(file_path)
                    print(f"[AUTO-CLEAN] Deleted old file: {file_path}")
            except Exception as e:
                print(f"[AUTO-CLEAN ERROR] {file_path} => {e}")
