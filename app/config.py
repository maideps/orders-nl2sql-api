"""Settings read from the environment (a local `.env` file is loaded if present)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(os.getenv("ORDERS_DB_PATH", "data/orders.db"))
RAW_CSV_PATH = Path("data/orders_raw.csv")
