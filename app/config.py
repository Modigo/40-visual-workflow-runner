import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./workflow_runner.db")
APP_ENV = os.getenv("APP_ENV", "development")
ENABLE_DEMO_NODE = os.getenv("ENABLE_DEMO_NODE", "false").lower() == "true"
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "1"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
PORT = int(os.getenv("PORT", "8000"))