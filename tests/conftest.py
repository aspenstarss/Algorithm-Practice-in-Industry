import os
import sys

import pytest

# 让 tests 能以仓库根为起点导入 paperBotV2 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paperBotV2.arxiv_daily import daily_store as _store


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    """所有测试禁止写真实 data 目录（CI 会把该目录提交/推送）。

    需要数据落盘的测试用 test_daily_store.store_dir 再覆盖一次即可。
    """
    monkeypatch.setattr(_store, "DATA_DIR", str(tmp_path / "data"))
