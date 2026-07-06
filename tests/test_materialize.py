import json

import pytest

from antfarm.cli import main
from helpers import TRIGGER_TEXT, critique_fixture, framing_fixture, scout_fixture

QUESTION = "What limits US solar growth through 2030?"


@pytest.fixture(autouse=True)
def _offline_embeddings(monkeypatch):
    monkeypatch.setenv("ANTFARM_EMBED", "hash")


def run_cli(corpus_dir, *argv, payload=None):
    args = list(argv) + ["--corpus", str(corpus_dir)]
    if payload is not None:
        path = corpus_dir.parent / "payload.json"
        path.write_text(json.dumps(payload))
        args += ["--input", str(path)]
    return main(args)


@pytest.fixture()
def surveyed(tmp_path):
    corpus_dir = tmp_path / "corpus"
    run = run_cli(corpus_dir, "run-new", "--question", QUESTION)["run"]
    rival = run_cli(corpus_dir, "harvest-framing", "--run", run,
                    payload=framing_fixture())["rivals"][0]
    run_cli(corpus_dir, "farm-init", "--run", run, "--farm", "A",
            "--hypothesis-text", rival["text"],
            "--persona", "officer", "--family", "opus")
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A", "--round", "1",
            "--family", "opus", "--persona", "officer",
            payload=scout_fixture(1, "CONTINUE"))
    run_cli(corpus_dir, "harvest-critique", "--run", run, "--farm", "A", "--round", "1",
            payload=critique_fixture())
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A", "--round", "2",
            "--family", "opus", "--persona", "officer",
            payload=scout_fixture(2, "CONCLUDE"))
    run_cli(corpus_dir, "farm-outcome", "--run", run, "--farm", "A",
            "--decision", "CONCLUDE")
    queue = run_cli(corpus_dir, "verification-queue")
    run_cli(corpus_dir, "harvest-verify", "--run", run, payload=[
        {"atom_id": q["id"], "verified": True, "evidence": "corroborated",
         "source": None} for q in queue])
    return corpus_dir, run


def test_materialize_builds_view_vault_and_exports(surveyed):
    corpus_dir, run = surveyed
    summary = run_cli(corpus_dir, "materialize", "--run", run)
    assert summary["view_size"] >= 1
    assert summary["pages"] == summary["view_size"]
    assert summary["farms_exported"] == ["A"]
    assert summary["tripwires_registered"] == 1

    trace = corpus_dir / "exports" / run / "A" / "trace.jsonl"
    lines = [json.loads(line) for line in trace.read_text().splitlines()]
    assert all(set(line) == {"turn", "role", "phase", "iteration", "content"}
               for line in lines)
    stats = json.loads((corpus_dir / "exports" / run / "A" / "stats.json").read_text())
    assert stats["coherence_label"] == "coherent"
    assert stats["outcome"]["ledger_clean"] is True
    assert stats["outcome"]["verification"]["atoms_emitted"] >= 3


def test_materialize_registers_high_triggers_as_tripwires(surveyed):
    corpus_dir, run = surveyed
    run_cli(corpus_dir, "materialize", "--run", run)
    tripwires = run_cli(corpus_dir, "tripwires-list")
    assert len(tripwires) == 1 and tripwires[0]["text"] == TRIGGER_TEXT
    assert tripwires[0]["watches"]  # it watches the farm's hypothesis
    # re-materializing must not duplicate the tripwire (content-hash identity)
    run_cli(corpus_dir, "materialize", "--run", run)
    assert len(run_cli(corpus_dir, "tripwires-list")) == 1


def test_materialized_store_answers_queries(surveyed):
    corpus_dir, run = surveyed
    run_cli(corpus_dir, "materialize", "--run", run)
    hits = run_cli(corpus_dir, "query", "--collection", "well",
                   "--text", "storage lags panel deployment")
    assert hits
