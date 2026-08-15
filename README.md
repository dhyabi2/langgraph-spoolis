# Verified outcomes for LangGraph payment tools

LangGraph's `interrupt()` can pause a graph before a payment tool runs, but the interrupt alone does not supply the verdict that should resume it. Human review works for exceptional cases. It does not scale as the routine decision point for agent payments.

This example puts a verified outcome in the loop. Spoolis compiles fulfillment criteria, verifies submitted evidence, and returns a signed Outcome Receipt. The graph reads `receipt.amounts.earned`, pauses before its payment tool, and resumes under a policy that binds the resume command to that receipt. The payment tool is a stub. It only prints what it would pay.

## What the example does

The graph uses the account-free Spoolis public sandbox to model a $10.00 task with 10 records at $1.00 each. Ten records are submitted. Eight include both required fields and two omit `status`. The deterministic checks produce 8 accepted records, 2 rejected records, and `$8.00` earned.

No real money moves. The sandbox demonstrates compilation, evidence verification, and receipt issuance. Deterministic checks and human-confirmed checks are live. AI-assisted verification is planned and is not live.

## Quickstart

Use Python 3.10 or newer and Node.js 20 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
npm install
python3 graph.py
npm run verify
```

`graph.py` writes the signed receipt to `outcome-receipt.json`. The final two commands should report `8.00 USD` and a local signature result with `"authentic": true`.

You can also open `notebook.ipynb` and run its cells from this directory.

## Architecture

```text
LangGraph runner
    |
    v
buy_records
    |  mint sandbox session
    |  compile criteria
    |  accept Spool
    |  submit two evidence items
    v
verify
    |  run Spoolis verification
    |  save signed receipt and amounts.earned
    v
payment_gate
    |  interrupt with receipt ID, result, and earned amount
    |  runner applies policy and sends Command(resume=...)
    v
pay tool
       print the exact earned amount, no real payment
```

The payment gate is separate from the verification node on purpose. LangGraph restarts an interrupted node from its beginning when it resumes. Keeping the network side effect in the preceding node prevents verification from running again during resume.

This example assumes `langgraph==1.2.11`. It uses a checkpointer and a stable thread ID because dynamic interrupts require both. The resume value becomes the return value of `interrupt()`. The runner uses the same thread ID and binds the resume value to the saved receipt ID.

## Verify the receipt independently

`verify_receipt.mjs` mirrors the Outcome Receipt documentation. It fetches the public trust set from `https://spoolis.com/.well-known/spoolis-keys.json`, selects the receipt's environment, and verifies the receipt with `@spoolis/receipt-verifier`.

```bash
node verify_receipt.mjs outcome-receipt.json
```

A valid Ed25519 signature shows that the receipt came from a trusted published key and was not altered. It does not prove that the underlying evidence is true, authorize payment, or establish settlement.

## Boundaries for production use

This is a sandbox integration draft, not a production payment system.

- The sandbox is account-free, demo-only, and does not move money.
- The in-memory LangGraph checkpointer is suitable for a short example. Use durable persistence in production.
- The sample runner accepts determinate `pass` and `partial` receipts, checks the receipt ID on resume, and passes the earned decimal string to a stub. A production buyer must define its own authorization, identity, replay, amount, and settlement policies.
- Verify the receipt signature before any consequential action. The local Node.js check is shown separately so each trust boundary stays visible.
- The built-in Spoolis settlement flow does not automatically settle a partial result. An external integration that acts on a partial receipt needs its own explicit authorization policy.

## Files

- `graph.py`: the StateGraph, sandbox client, interrupt gate, and payment stub.
- `verify_receipt.mjs`: independent signature verification against the published trust set.
- `notebook.ipynb`: a cell-by-cell walkthrough of the same graph.
- `requirements.txt` and `package.json`: minimal pinned dependencies.
