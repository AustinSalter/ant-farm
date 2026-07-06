import json

import pytest

from antfarm import farm as farm_mod
from antfarm.cli import main
from antfarm.emission import export_schemas
from antfarm.schema import atom_id
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
    monkeypatch.setenv("ANTFARM_EMBED", "hash")


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
            "--hypothesis-text", rival["text"],
            "--persona", "a municipal procurement officer", "--family", "opus")
    return run, rival


def test_full_farm_round_trip_gates_conclude(corpus_dir):
    run, rival = _start_farm(corpus_dir)

    r1 = scout_fixture(1, "CONTINUE")
    h1 = run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A",
                 "--round", "1", "--family", "opus", "--persona", "officer",
                 payload=r1)
    assert h1["atom_ids"] and not h1["rejected"]
    gate1 = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A",
                    "--decision", "CONTINUE")
    assert gate1["decision"] == "CONTINUE"

    run_cli(corpus_dir, "harvest-critique", "--run", run, "--farm", "A",
            "--round", "1", payload=critique_fixture())
    # premature CONCLUDE now blocks: standing undercutters + no HIGH trigger yet
    blocked = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A",
                      "--decision", "CONCLUDE")
    assert blocked["decision"] == "CONTINUE" and blocked["forced"]

    r2 = scout_fixture(2, "CONCLUDE")
    run_cli(corpus_dir, "harvest-scout", "--run", run, "--farm", "A",
            "--round", "2", "--family", "opus", "--persona", "officer", payload=r2)
    gate2 = run_cli(corpus_dir, "gate", "--run", run, "--farm", "A",
                    "--decision", "CONCLUDE")
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


def test_farm_init_derives_hypothesis_id_from_its_own_harvest(corpus_dir):
    run = run_cli(corpus_dir, "run-new", "--question", QUESTION)["run"]
    run_cli(corpus_dir, "harvest-framing", "--run", run, payload=framing_fixture())
    result = run_cli(corpus_dir, "farm-init", "--run", run, "--farm", "Z",
                     "--hypothesis-text", HYPOTHESIS_TEXT,
                     "--persona", "a municipal procurement officer",
                     "--family", "opus")
    canonical = atom_id("hypothesis", HYPOTHESIS_TEXT)
    assert result["hypothesis_id"] == canonical
    assert result["hypothesis_id"].startswith("h-")

    d = farm_mod.farm_dir(corpus_dir, run, "Z")
    meta = farm_mod.read_meta(d)
    assert meta.hypothesis_id == canonical


def test_farm_init_rejects_non_self_contained_hypothesis_text(corpus_dir):
    run = run_cli(corpus_dir, "run-new", "--question", QUESTION)["run"]
    run_cli(corpus_dir, "harvest-framing", "--run", run, payload=framing_fixture())
    with pytest.raises(SystemExit):
        run_cli(corpus_dir, "farm-init", "--run", run, "--farm", "Z",
                "--hypothesis-text", "This proves the thesis.",
                "--persona", "a municipal procurement officer", "--family", "opus")


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


def test_tripwire_fire_unknown_id_is_reported_not_swallowed(corpus_dir):
    run, _ = _start_farm(corpus_dir)
    result = run_cli(corpus_dir, "tripwire-fire", "--run", run,
                     "--id", "w-000000000000",
                     payload={"evidence": "A storage glut arrived in 2027."})
    assert result == {"affected": [], "unknown_tripwire": True}
    # nothing was appended: an unknown id must not leave an orphan evidence node
    assert not (corpus_dir / "runs" / run / "p0-sentinel.jsonl").exists()


def test_embedding_caches_are_backend_scoped(corpus_dir, monkeypatch):
    from antfarm.cli import get_embed

    corpus_dir.mkdir(parents=True)
    hash_embedder = get_embed(corpus_dir)
    vecs = hash_embedder(["Storage constraints bind solar growth through 2030."])
    assert len(vecs[0]) == 256
    # the hash backend writes its own cache file, never the chroma one
    assert (corpus_dir / "emb-cache-hash.json").exists()
    assert not (corpus_dir / "emb-cache.json").exists()
