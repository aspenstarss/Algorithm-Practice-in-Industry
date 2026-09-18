"""conf_summary 的路径唯一来源（结果库与数据目录）。"""
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_PATH = SCRIPT_DIR / "data" / "results.json"
DATA_DIR = SCRIPT_DIR / "data"
