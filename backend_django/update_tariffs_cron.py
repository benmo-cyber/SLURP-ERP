"""
Cron job script to update tariffs from Flexport
Run this every Sunday night (e.g., via Windows Task Scheduler or cron)
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Import and run the update
from erp_core.flexport_tariff import update_tariffs

if __name__ == '__main__':
    print(f"Running Flexport tariff update at {datetime.now()}")
    updated, errors = update_tariffs()
    print(f"Update complete: {updated} items updated, {errors} errors")
    sys.exit(0 if errors == 0 else 1)
