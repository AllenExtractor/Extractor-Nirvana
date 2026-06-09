import os
import time
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler

# Define the directory where temporary files are stored
TEMP_DIR = Path("/app/tmp")  # Adjust this path if your temp files are elsewhere

# Ensure the directory exists
if not TEMP_DIR.exists():
    TEMP_DIR.mkdir(parents=True)

def clean_old_files():
    # Get the current time in seconds
    current_time = time.time()
    # 30 minutes = 30 * 60 seconds
    thirty_minutes_ago = current_time - (30 * 60)

    # Iterate over all files in the temp directory
    for file_path in TEMP_DIR.iterdir():
        if file_path.is_file():  # Ensure it's a file, not a directory
            # Get the file's creation time (or last modification time if creation time isn't available)
            file_stat = file_path.stat()
            creation_time = file_stat.st_ctime  # On Heroku, this might reflect creation time
            # If the file is older than 30 minutes, delete it
            if creation_time < thirty_minutes_ago:
                try:
                    file_path.unlink()  # Delete the file
                    print(f"Deleted old file: {file_path}")
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")

def start_cleanup_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(clean_old_files, 'interval', minutes=10)  # Run every 10 minutes
    scheduler.start()
    print("Cleanup scheduler started.")
    return scheduler  # Return the scheduler object to keep it alive

if __name__ == "__main__":
    scheduler = start_cleanup_scheduler()
    try:
        # Keep the script running
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
