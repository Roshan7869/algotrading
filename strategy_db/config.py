import os

STRATEGY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "strategy")
DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "trading_strategies"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K_DEFAULT = 5
