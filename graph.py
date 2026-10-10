"""A minimal verified-outcome-in-the-loop LangGraph example."""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal
from typing import Any, NotRequired, TypedDict
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

API_BASE = os.environ.get("SPOOLIS_API_BASE", "https://spoolis.com").rstrip("/")
SOURCE = (
    "Buy 10 research records for $10.00. Each accepted record earns $1.00. "
    "Exactly 10 records are required. Every record must include id and status."
)
CONDITIONS = [
    {
        "description": "Exactly 10 records",
        "required": True,
        "verification_method": "deterministic",
        "deterministic_check": {"checker": "row_count", "expected": 10},
    },
    {
        "description": "Each record must include id and status",
        "required": True,
        "verification_method": "deterministic",
        "deterministic_check": {
            "checker": "completeness",
            "required_fields": ["id", "status"],
        },
    },
]


class GraphState(TypedDict):
    token: NotRequired[str]
    spool_id: NotRequired[str]
    receipt: NotRequired[dict[str, Any]]
    earned: NotRequired[str]
    asset: NotRequired[str]
    payment_message: NotRequired[str]


def post(path: str, token: str | None = None, body: Any = None) -> dict[str, Any]:
    headers = {"accept": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["content-type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = Request(f"{API_BASE}{path}", data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Spoolis returned HTTP {error.code}: {detail}") from error
    if result.get("status") == "limit_reached":
        raise RuntimeError(result.get("message", "The sandbox limit was reached."))
    return result


def buy_records(_: GraphState) -> GraphState:
    session = post("/api/sandbox/session")
    token = session["token"]
    compiled = post(
        "/api/sandbox/compile",
        token,
        {
            "source": SOURCE,
            "economics": {
                "unitization": {"total_units": 10, "unit_amount_cents": 100}
            },
            "conditions": CONDITIONS,
            "declared_actor_type": "human",
        },
    )
    spool = compiled["spool"]
    condition_ids = {
        condition["deterministic_check"]["checker"]: condition["id"]
        for condition in spool["conditions"]
        if condition.get("deterministic_check")
    }
    if set(condition_ids) < {"row_count", "completeness"}:
        raise RuntimeError("The compiled Spool is missing a deterministic condition.")

    spool_id = spool["id"]
    post(f"/api/sandbox/spools/{spool_id}/accept", token)
    rows = [
        ({"id": f"record-{index + 1}", "status": "accepted"}
         if index < 8 else {"id": f"record-{index + 1}"})
        for index in range(10)
    ]
    evidence_path = f"/api/sandbox/spools/{spool_id}/evidence"
    post(
        evidence_path,
        token,
        {
            "condition_id": condition_ids["row_count"],
            "type": "dataset",
            "source": "inline LangGraph example rows",
            "metadata": {"rows": rows},
        },
    )
    post(
        evidence_path,
        token,
        {
            "condition_id": condition_ids["completeness"],
            "type": "dataset",
            "source": "inline LangGraph example rows with two missing status fields",
            "metadata": {"rows": rows},
        },
    )
    return {"token": token, "spool_id": spool_id}


def verify(state: GraphState) -> GraphState:
    result = post(
        f"/api/sandbox/spools/{state['spool_id']}/verify", state["token"]
    )
    receipt = result.get("receipt")
    if not receipt:
        raise RuntimeError("Verification completed without an Outcome Receipt.")
    amounts = receipt["amounts"]
    return {
        "receipt": receipt,
        "earned": amounts["earned"],
        "asset": amounts["asset"],
    }


def payment_gate(state: GraphState) -> GraphState:
    receipt = state["receipt"]
    decision = interrupt(
        {
            "kind": "verified_outcome",
            "receipt_id": receipt["id"],
            "result": receipt["result"],
            "earned": state["earned"],
            "asset": state["asset"],
        }
    )
    if not isinstance(decision, dict) or decision.get("receipt_id") != receipt["id"]:
        raise ValueError("The resume value must identify the verified receipt.")
    return {}


@tool
def pay(amount: str, asset: str, config: RunnableConfig) -> str:
    """Print the exact amount that a payment adapter would receive.

    For the feeless Nano (XNO) rail this returns a spendable payment URI of the
    form ``nano:<account>?amount=<raw>`` that a customer can open in any Nano
    wallet to settle instantly with no network fee. For any other asset it keeps
    the original WOULD-pay stub behaviour, because only XNO has a wired adapter.

    The receiving ``nano_account`` is taken from ``config["configurable"]``
    (live mode) or the ``NANO_ACCOUNT`` environment variable (a sandbox
    placeholder by default), so a tenant controls the destination and no key is
    ever required of the caller.
    """
    if asset == "XNO":
        account = (
            config["configurable"].get("nano_account")
            or os.environ.get("NANO_ACCOUNT")
            or "nano_1placeholderaccount0000000000000000000000000000000000"
        )
        amount_raw = int(Decimal(amount) * Decimal(10) ** 30)
        return f"nano:{account}?amount={amount_raw}"

    # This example never moves money. A real adapter needs its own authorization policy.
    message = f"WOULD pay {amount} {asset}. No real money moved."
    print(message)
    return message


def pay_node(state: GraphState) -> GraphState:
    config = {"configurable": state.get("config", {})}
    message = pay.invoke(
        {"amount": state["earned"], "asset": state["asset"]},
        config=config,
    )
    return {"payment_message": message}


def build_graph():
    builder = StateGraph(GraphState)
    builder.add_node("buy_records", buy_records)
    builder.add_node("verify", verify)
    builder.add_node("payment_gate", payment_gate)
    builder.add_node("pay", pay_node)
    builder.add_edge(START, "buy_records")
    builder.add_edge("buy_records", "verify")
    builder.add_edge("verify", "payment_gate")
    builder.add_edge("payment_gate", "pay")
    builder.add_edge("pay", END)
    return builder.compile(checkpointer=InMemorySaver())


def run_demo() -> dict[str, Any]:
    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    paused = graph.invoke({}, config=config)
    interruption = paused["__interrupt__"][0].value

    if interruption["result"] not in {"pass", "partial"}:
        raise RuntimeError(f"The verified result is {interruption['result']}; payment held.")
    if Decimal(interruption["earned"]) < 0:
        raise RuntimeError("The verified earned amount cannot be negative.")

    return graph.invoke(
        Command(resume={"receipt_id": interruption["receipt_id"]}), config=config
    )


if __name__ == "__main__":
    final = run_demo()
    with open("outcome-receipt.json", "w", encoding="utf-8") as receipt_file:
        json.dump(final["receipt"], receipt_file, indent=2)
        receipt_file.write("\n")
    print(f"Receipt: {final['receipt']['id']}")
    print(f"Earned: {final['earned']} {final['asset']}")

