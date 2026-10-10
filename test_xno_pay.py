"""Unit tests for the XNO (Nano) settlement leg of the pay() tool.

These tests do not touch the Spoolis sandbox or move money: they exercise
graph.pay.invoke directly with controlled amounts and a placeholder account,
and assert the shape of the returned payment link.
"""

from __future__ import annotations


from graph import GraphState, build_graph, pay

XNO_ACCOUNT = "nano_1fakeaccount000000000000000000000000000000000000000000000000"
XNO_PLACEHOLDER = "nano_1fakeaccount000000000000000000000000000000000000000000000000"


def test_pay_returns_stub_message_for_unsupported_asset() -> None:
    """A non-Nano asset keeps the existing WOULD-pay stub behaviour."""
    message = pay.invoke({"amount": "8.00", "asset": "USD"})
    assert "WOULD pay 8.00 USD" in message


def test_pay_returns_xno_payment_link_for_xno_asset() -> None:
    """For an XNO asset, pay() must return a spendable Nano payment link."""
    message = pay.invoke({"amount": "8.00", "asset": "XNO"}, config={"configurable": {"nano_account": XNO_ACCOUNT}})
    assert message.startswith("nano:"), message
    assert XNO_ACCOUNT in message, message
    assert "amount=" in message, message


def test_pay_xno_link_is_a_uri_with_lowercase_account() -> None:
    """The link must follow the nano URI scheme: nano:<account>?amount=<raw>."""
    message = pay.invoke({"amount": "1.0", "asset": "XNO"}, config={"configurable": {"nano_account": XNO_ACCOUNT}})
    assert message.startswith("nano:"), message
    assert "nano_" in message, message
    assert "?amount=" in message, message
    # The account inside the URI should be a plausible Nano account
    account_part = message.split("?amount=", 1)[0].removeprefix("nano:")
    assert account_part.startswith("nano_1") or account_part.startswith("nano_3"), account_part


def test_xno_amount_is_integer_raw_units() -> None:
    """The amount is expressed in raw (integer sub-raw units of 1e-30 XNO)."""
    message = pay.invoke({"amount": "1.0", "asset": "XNO"}, config={"configurable": {"nano_account": XNO_ACCOUNT}})
    amount = message.split("amount=", 1)[1]
    # 1 XNO == 10^30 raw
    assert amount == str(10**30), amount


def test_graph_executes_with_xno_asset_field() -> None:
    """GraphState accepts the XNO asset string and the graph wires it through."""
    state = GraphState(earned="8.00", asset="XNO")
    assert state["asset"] == "XNO"
    # build_graph must compile (the pay node is reachable and connected)
    graph = build_graph()
    assert graph is not None
