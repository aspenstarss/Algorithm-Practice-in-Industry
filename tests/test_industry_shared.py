"""industry_practice 的共享日期解析测试（坏日期显式报错，不再伪装成今天）。"""
import pytest

from paperBotV2.industry_practice import generate_industry_html as gi


def test_get_sortable_date_supported_formats():
    assert gi.get_sortable_date("2026-09-19") == "2026-09-19"
    assert gi.get_sortable_date("2026.09.19") == "2026-09-19"
    assert gi.get_sortable_date("09/19/2026") == "2026-09-19"
    assert gi.get_sortable_date("2026年9月19日") == "2026-09-19"
    assert gi.get_sortable_date("09-19-26") == "2026-09-19"


def test_get_sortable_date_rejects_unrecognized():
    with pytest.raises(ValueError):
        gi.get_sortable_date("2026")
    with pytest.raises(ValueError):
        gi.get_sortable_date("")
    with pytest.raises(ValueError):
        gi.get_sortable_date("Sept 5, 2026")
