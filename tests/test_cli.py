import json

import pytest

from antfarm.cli import main
from antfarm.emission import export_schemas
from helpers import (
    CLAIM_TEXT,
    HYPOTHESIS_TEXT,
    critique_fixture,
    framing_fixture,
    scout_fixture,
)

QUESTION = "What limits US solar growth through 2030?"


@pytest.fixture(autouse=True)
def _offline_embeddings(monkeypatch):
    monkeypatch.setenv("ANTFARM_EMBED", "trigram")


@pytest.fixture()
def corpus_dir(tmp_path):
    return tmp_path / "corpus"


def run_cli(corpus_dir, *argv, payload=None):
    args = list(argv) + ["--corpus", str(corpus_dir)]
    if payload is not None:
        path = corpus_dir.parent / "payload.json"
        path.write_text(json.dumps(payload))
        args += ["--input", str(path)]
    return main(args)


def test_schemas_matches_export(corpus_dir, capsys):
    result = run_cli(corpus_dir, "schemas")
    assert result == export_schemas()
    assert json.loads(capsys.readouterr().out) == result


def test_run_new_binds_question_and_increments(corpus_dir):
    first = run_cli(corpus_dir, "run-new", "--question", QUESTION)
    assert first == {"run": "r0001", "question_id": first["question_id"],
                     "first_run": True}
    second = run_cli(corpus_dir, "run-new", "--question", QUESTION)
    assert second["run"] == "r0002" and second["first_run"] is False
    with pytest.raises(SystemExit):
        run_cli(corpus_dir, "run-new", "--question", "A different question entirely?")


def _start_farm(corpus_dir):
    run = run_cli(corpus_dir, "run-new", "--question", QUESTION)["run"]
    harvested = run_cli(corpus_dir, "harvest-framing", "--run", run,
                        payload=framing_fixture())
    rival = harvested["rivals"][0]
    run_cli(corpus_dir, "farm-init", "--run", run, "--farm", "A",
            "--hypothesis-id", rival["id"], "--hypothesis-text", rival["text"],
            "--persona", "a municipal procurement officer", "--family", "opus")
    return run, rival


def test_full_farm_round_trip_gates_conclude(corpus_dir):
    run, rival = _start_farm(corpus_dir)

    r1 = scout_fixture(1, "CONTINUE")
    h1 = run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A",
                 "--round", "1", "--family", "opus", "--persona", "officer",
                 payload=r1)
    assert h1["atom_ids"] and not h1["rejected"]
    gate1 = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A", payload=r1)
    assert gate1["decision"] == "CONTINUE"

    run_cli(corpus_dir, "harvest-critique", "--run", run, "--farm", "A",
            "--round", "1", payload=critique_fixture())
    # premature CONCLUDE now blocks: standing undercutters + no HIGH trigger yet
    blocked = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A",
                      payload=scout_fixture(1, "CONCLUDE"))
    assert blocked["decision"] == "CONTINUE" and blocked["forced"]

    r2 = scout_fixture(2, "CONCLUDE")
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A",
            "--round", "2", "--family", "opus", "--persona", "officer", payload=r2)
    gate2 = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A", payload=r2)
    assert gate2 == {"decision": "CONCLUDE", "forced": False, "reasons": []}
    run_cli(corpus_dir, "farm-outcome", "--run", run, "--farm", "A",
            "--decision", "CONCLUDE")

    queue = run_cli(corpus_dir, "verification-queue")
    assert any(q["text"] == CLAIM_TEXT for q in queue)
    claim_id = next(q["id"] for q in queue if q["text"] == CLAIM_TEXT)
    verified = run_cli(corpus_dir, "harvest-verify", "--run", run, payload=[
        {"atom_id": claim_id, "verified": True,
         "evidence": "CAISO reports corroborate.", "source": "caiso.com"}])
    assert verified["verified"] == [claim_id]


def test_probe_and_query_before_first_materialize(corpus_dir):
    run, rival = _start_farm(corpus_dir)
    dup = run_cli(corpus_dir, "probe", payload={"text": HYPOTHESIS_TEXT})
    assert dup["novel"] is False
    novel = run_cli(corpus_dir, "probe",
                    payload={"text": "zqx wvj kkp qqe zzt xxr wwy vvu"})
    assert novel["novel"] is True
    hits = run_cli(corpus_dir, "query", "--collection", "view", "--text", "storage")
    assert hits == []  # no chroma store before first materialize


def test_stitch_and_tripwire_flow(corpus_dir):
    run, rival = _start_farm(corpus_dir)
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A", "--round", "2",
            "--family", "opus", "--persona", "officer",
            payload=scout_fixture(2, "CONCLUDE"))
    stitch = {
        "ach": [], "investigations": [],
        "declaration_kind": "basin",
        "declaration_summary": "Storage thesis holds.",
        "positions": [{"hypothesis_text": HYPOTHESIS_TEXT, "condition": None}],
        "dissolve": {"dissolved": False, "diagnosis": None, "replacement_question": None},
    }
    result = run_cli(corpus_dir, "harvest-stitch", "--run", run, payload=stitch)
    assert result["declaration"]["kind"] == "basin"
    assert "e_band" in result["declaration"]
    declaration_path = corpus_dir / "runs" / run / "declaration.json"
    assert declaration_path.exists()
    brief = run_cli(corpus_dir, "stitch-brief", "--run", run)
    assert brief["farms"][0]["farm"] == "A"
