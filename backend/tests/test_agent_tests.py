from types import SimpleNamespace

import pytest

from app.modules.agent_tests import _is_cart_write, _task_check, RunResult


def req(url: str, body: str = ""):
    return SimpleNamespace(url=url, post_data=body)


@pytest.mark.parametrize("url, body", [
    ("https://shop.example/cart/add.js", "id=123&quantity=1"),  # Shopify
    ("https://shop.example/product/mug/", "add-to-cart=42&quantity=1"),  # WooCommerce
    ("https://shop.example/basket/", ""),
    ("https://shop.example/api/add_to_bag", "{}"),
])
def test_cart_writes_allowed(url, body):
    assert _is_cart_write(req(url, body))


@pytest.mark.parametrize("url, body", [
    ("https://shop.example/checkout", "add-to-cart=1"),
    ("https://shop.example/cart/checkout/payment", ""),
    ("https://shop.example/order/confirm", ""),
    ("https://rest.example/booking", "date=2026-11-01&party=2"),
    ("https://site.example/contact", "name=Alex"),
    ("https://site.example/newsletter", "email=a@b.c"),
])
def test_commit_requests_blocked(url, body):
    assert not _is_cart_write(req(url, body))


def test_task_check_rates():
    ok = RunResult("find hours", 1, success=True, steps=[{"url": "u"}])
    bad = RunResult("find hours", 2, success=False, failure_reason="login wall", steps=[{"url": "https://x/login"}])
    check = _task_check("find hours", [ok, bad])
    assert check.status == "partial"
    assert check.evidence["success_rate"] == 0.5
    assert check.evidence["runs"][1]["stuck_at"] == "https://x/login"
    assert _task_check("t", [ok]).status == "pass"
    assert _task_check("t", [bad]).status == "fail"
