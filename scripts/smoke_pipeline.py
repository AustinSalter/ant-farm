"""End-to-end smoke test for the survey pipeline's Python side.

Drives the CLI exactly as workflows/survey.js does - fixture agent outputs in,
JSON out - through: run-new -> framing -> two farms (one CONCLUDE, one CONCEDE)
with critique and gates -> verification floor -> stitch -> probe -> materialize.
Offline: ANTFARM_EMBED=hash, no model downloads.

Run: uv run python scripts/smoke_pipeline.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKS: list[str] = []


def check(name: str, condition: bool) -> None:
    print(f"  [{'ok' if condition else 'FAIL'}] {name}")
    CHECKS.append(name)
    if not condition:
        sys.exit(f"pipeline smoke failed at: {name}")


def cli(corpus: Path, *argv: str, payload=None):
    cmd = [sys.executable, "-m", "antfarm", *argv, "--corpus", str(corpus)]
    kwargs = {}
    if payload is not None:
        cmd += ["--input", "-"]
        kwargs["input"] = json.dumps(payload)
    env = {**os.environ, "ANTFARM_EMBED": "hash"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, **kwargs)
    if proc.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{proc.stderr}")
    return json.loads(proc.stdout)


QUESTION = "Is rooftop solar a good investment for US homeowners?"
HYP_A = "Rooftop solar pays back within ten years in most US states."
HYP_B = "Rooftop solar only pays back where net metering survives."
NULL = "Rooftop solar payback is too variable for any general claim."
CLAIM_A = "Residential solar payback periods fell below ten years in over thirty states."
EVIDENCE_A = "Lawrence Berkeley National Laboratory tracked 2024 paybacks averaging nine years."
CRITIQUE_A = "Payback estimates ignore inverter replacement costs at year twelve."
PREMORTEM_A = "The payback thesis failed because net metering rollbacks spread beyond California."
REBUT_1 = "Inverter replacement adds under one year to average payback in current models."
REBUT_2 = "Net metering rollback proposals stalled in most state legislatures through 2026."
TRIGGER_A = (
    "Three additional states adopting California-style net billing by 2027 "
    "falsifies the payback thesis."
)

FRAMING = {
    "stasis": "quality", "altitude": "US household level, 10-year horizon",
    "dissolve": {"dissolved": False, "diagnosis": None, "replacement_question": None},
    "reference_class": "household capital-improvement investments",
    "base_rate": "most such investments recoup within their advertised window",
    "zwicky_dimensions": [{"name": "policy", "values": ["net metering", "net billing"]},
                          {"name": "region", "values": ["sunbelt", "northern"]}],
    "incoherent_cells": [],
    "rivals": [{"text": HYP_A, "is_null": False, "warm_started": False},
               {"text": HYP_B, "is_null": False, "warm_started": False},
               {"text": NULL, "is_null": True, "warm_started": False}],
}


def scout_a(round_n: int, decision: str) -> dict:
    base = {
        "sublation": [], "expansion": f"Round {round_n}: payback analysis.",
        "atoms": [{"type": "claim", "text": CLAIM_A, "strength": None,
                   "diagnosticity": None},
                  {"type": "evidence", "text": EVIDENCE_A, "strength": 4,
                   "diagnosticity": "high"}],
        "edges": [{"src": EVIDENCE_A, "dst": CLAIM_A, "rel": "supports",
                   "warrant": "measured paybacks license the general claim"}],
        "falsification_triggers": [],
        "compressed_state": f"Thesis after round {round_n}: sub-decade payback holds.",
        "confidence_r": "med", "confidence_c": "med",
        "ledger_entry": None, "decision": decision, "died_because": None,
    }
    if round_n >= 2:
        base["sublation"] = [
            {"critique": CRITIQUE_A, "disposition": "rebutted", "response": REBUT_1},
            {"critique": PREMORTEM_A, "disposition": "rebutted", "response": REBUT_2}]
        base["atoms"] = [{"type": "claim", "text": REBUT_1, "strength": None,
                          "diagnosticity": None},
                         {"type": "claim", "text": REBUT_2, "strength": None,
                          "diagnosticity": None}]
        base["edges"] = [{"src": REBUT_1, "dst": CRITIQUE_A, "rel": "rebuts",
                          "warrant": None},
                         {"src": REBUT_2, "dst": PREMORTEM_A, "rel": "rebuts",
                          "warrant": None}]
        base["falsification_triggers"] = [{"text": TRIGGER_A, "severity": "high"}]
        base["ledger_entry"] = {"trigger": "round 1 critique",
                                "change": "rebutted cost and policy challenges",
                                "novel_content": True}
    return base


CRITIQUE = {
    "findings": [{"target_text": CLAIM_A, "kind": "warrant_probe",
                  "classification": "undercutting", "severity": "high",
                  "text": CRITIQUE_A}],
    "premortem": PREMORTEM_A,
    "summary": "Cost omission probe plus policy premortem.",
}

SCOUT_B = {
    "sublation": [], "expansion": "Round 1: policy-dependence analysis.",
    "atoms": [{"type": "claim",
               "text": "Net billing states show payback periods beyond fifteen years.",
               "strength": None, "diagnosticity": None}],
    "edges": [], "falsification_triggers": [],
    "compressed_state": "Thesis: policy dependence dominates, but the general "
                        "payback claim explains the same evidence.",
    "confidence_r": "low", "confidence_c": "med",
    "ledger_entry": None, "decision": "CONCEDE",
    "died_because": "the general payback thesis explains the evidence more simply",
}

STITCH = {
    "ach": [{"evidence_text": EVIDENCE_A, "hypothesis_text": HYP_A,
             "consistency": "consistent"},
            {"evidence_text": EVIDENCE_A, "hypothesis_text": NULL,
             "consistency": "inconsistent"}],
    "investigations": [],
    "declaration_kind": "basin",
    "declaration_summary": "The sub-decade payback basin dominates; policy is the crux.",
    "positions": [{"hypothesis_text": HYP_A, "condition": None}],
    "dissolve": {"dissolved": False, "diagnosis": None, "replacement_question": None},
}

SWAP = {"turns": [
    {"phase": "expand", "iteration": 2, "content": "As an auditor: check the cost model."},
    {"phase": "compress", "iteration": 2, "content": "Audited thesis: payback holds."}]}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        corpus = Path(tmp) / "corpus"

        print("setup + framing")
        setup = cli(corpus, "run-new", "--question", QUESTION)
        run = setup["run"]
        check("first run allocated r0001", run == "r0001" and setup["first_run"])
        check("schemas export includes every agent output",
              "scout_round" in cli(corpus, "schemas"))
        framed = cli(corpus, "harvest-framing", "--run", run, payload=FRAMING)
        check("three rivals harvested incl. null", len(framed["rivals"]) == 3)
        for farm, rival in (("A", framed["rivals"][0]), ("B", framed["rivals"][1])):
            cli(corpus, "farm-init", "--run", run, "--farm", farm,
                "--hypothesis-text", rival["text"],
                "--persona", "an energy analyst", "--family", "opus")

        print("farm A: continue -> critique -> sublate -> conclude")
        r1 = scout_a(1, "CONTINUE")
        cli(corpus, "harvest-scout", "--run", run, "--farm", "A", "--round", "1",
            "--family", "opus", "--persona", "analyst", payload=r1)
        gate1 = cli(corpus, "gate", "--run", run, "--farm", "A",
                    "--decision", "CONTINUE")
        check("round 1 gate says CONTINUE", gate1["decision"] == "CONTINUE")
        cli(corpus, "harvest-critique", "--run", run, "--farm", "A", "--round", "1",
            payload=CRITIQUE)
        blocked = cli(corpus, "gate", "--run", run, "--farm", "A",
                      "--decision", "CONCLUDE")
        check("premature CONCLUDE is blocked", blocked["decision"] == "CONTINUE"
              and blocked["forced"])
        r2 = scout_a(2, "CONCLUDE")
        cli(corpus, "harvest-scout", "--run", run, "--farm", "A", "--round", "2",
            "--family", "opus", "--persona", "analyst", payload=r2)
        gate2 = cli(corpus, "gate", "--run", run, "--farm", "A",
                    "--decision", "CONCLUDE")
        check("sublated CONCLUDE passes the gate", gate2["decision"] == "CONCLUDE")
        cli(corpus, "farm-outcome", "--run", run, "--farm", "A",
            "--decision", "CONCLUDE")

        print("farm B: honest concession")
        cli(corpus, "harvest-scout", "--run", run, "--farm", "B", "--round", "1",
            "--family", "sonnet", "--persona", "analyst", payload=SCOUT_B)
        gate_b = cli(corpus, "gate", "--run", run, "--farm", "B",
                     "--decision", "CONCEDE")
        check("CONCEDE passes through the gate", gate_b["decision"] == "CONCEDE")
        cli(corpus, "farm-outcome", "--run", run, "--farm", "B", "--decision",
            "CONCEDE", "--died-because", SCOUT_B["died_because"])

        print("verification floor + stitch")
        queue = cli(corpus, "verification-queue")
        check("verification queue is populated", len(queue) >= 2)
        cli(corpus, "harvest-verify", "--run", run, payload=[
            {"atom_id": item["id"], "verified": True,
             "evidence": "independently corroborated", "source": "example.org"}
            for item in queue])
        stitched = cli(corpus, "harvest-stitch", "--run", run, payload=STITCH)
        check("declaration computed with ACH winner and E band",
              stitched["declaration"]["kind"] == "basin"
              and stitched["declaration"]["ach"]["winner"] is not None
              and stitched["declaration"]["e_band"] in ("low", "med", "high"))

        print("holes + materialize + counterfactual")
        dup = cli(corpus, "probe", payload={"text": HYP_A})
        novel = cli(corpus, "probe",
                    payload={"text": "zqx wvj kkp qqe zzt xxr wwy vvu"})
        check("probe separates duplicate from novel",
              dup["novel"] is False and novel["novel"] is True)
        summary = cli(corpus, "materialize", "--run", run)
        check("view materialized with pages", summary["view_size"] >= 1
              and summary["pages"] == summary["view_size"])
        check("HIGH trigger registered as tripwire",
              summary["tripwires_registered"] >= 1
              and len(cli(corpus, "tripwires-list")) >= 1)
        stats_b = json.loads(
            (corpus / "exports" / run / "B" / "stats.json").read_text())
        check("CONCEDE exports as conceded, never degraded",
              stats_b["coherence_label"] == "conceded")
        trace_a = corpus / "exports" / run / "A" / "trace.jsonl"
        lines = [json.loads(line) for line in trace_a.read_text().splitlines()]
        check("keel trace lines carry exactly the five schema keys",
              all(set(line) == {"turn", "role", "phase", "iteration", "content"}
                  for line in lines))
        brief = cli(corpus, "brief")
        check("warm brief carries the conceded hypothesis",
              any(c["text"] == HYP_B for c in brief["conceded"]))
        pkg = cli(corpus, "persona-swap-prepare", "--run", run, "--farm", "A",
                  "--start-iteration", "2")
        check("persona-swap package is eligible", pkg["eligible"] is True)
        swapped = cli(corpus, "persona-swap-write", "--run", run, "--farm", "A",
                      "--start-iteration", "2", payload=SWAP)
        check("persona-swap counterfactual written", swapped["turns"] >= 4)

        second = cli(corpus, "run-new", "--question", QUESTION)
        check("second run resumes the corpus", second["run"] == "r0002"
              and second["first_run"] is False)

    print(f"\npipeline smoke passed: {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
