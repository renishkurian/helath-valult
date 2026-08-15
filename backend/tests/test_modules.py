"""Unit tests for per-user module enable/disable helpers."""
from app import modules


def test_parse_enabled_modules_none_means_all():
    assert modules.parse_enabled_modules(None) is None
    assert modules.parse_enabled_modules("") is None
    assert modules.parse_enabled_modules("[]") is None


def test_parse_enabled_modules_filters_unknown():
    raw = modules.serialize_enabled_modules(["finance", "diary", "nope"])
    assert raw is not None
    assert modules.parse_enabled_modules(raw) == ["finance", "diary"]


def test_serialize_all_becomes_null():
    assert modules.serialize_enabled_modules(list(modules.DEFAULT_MODULE_KEYS)) is None


def test_admin_module_for_path():
    assert modules.admin_module_for_path("/admin/diary") == "diary"
    assert modules.admin_module_for_path("/admin/diary/add") == "diary"
    assert modules.admin_module_for_path("/admin/finance/stats") == "finance"
    assert modules.admin_module_for_path("/admin/modules") is None
    assert modules.admin_module_for_path("/admin/login") is None
    assert modules.admin_module_for_path("/admin/signup") is None
    assert modules.admin_module_for_path("/admin") == "health"


def test_diary_in_defaults():
    assert "diary" in modules.DEFAULT_MODULE_KEYS
    assert modules.MODULE_LABELS["diary"] == "Digital Diary"
