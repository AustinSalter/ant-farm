from antfarm.emission import CritiqueFinding, CritiqueReport, TriggerEmission
from antfarm.farm import (
    FarmMeta,
    append_ledger,
    append_triggers,
    append_turns,
    init_farm,
    last_compressed,
    next_turn_index,
    read_ledger,
    read_meta,
    read_outcome,
    read_triggers,
    read_turns,
    write_critique,
    write_outcome,
)
from antfarm.transcript import LedgerEntry, Turn
from helpers import make_vantage  # noqa: F401 - ensures helpers imports stay shared

META = FarmMeta(farm="A", hypothesis_id="h-000000000001",
                hypothesis_text="Storage binds solar growth.",
                persona="a municipal procurement officer", family="opus",
                question_id="q-1", question_text="What limits solar growth?")


def test_init_farm_writes_meta_and_brief_turn(tmp_path):
    d = init_farm(tmp_path, "r0001", "A", META)
    assert read_meta(d) == META
    turns = read_turns(d)
    assert len(turns) == 1 and turns[0].role == "user" and turns[0].turn == 0
    assert META.hypothesis_text in turns[0].content
    assert META.persona in turns[0].content
    assert next_turn_index(d) == 1


def test_turn_ledger_trigger_roundtrips(tmp_path):
    d = init_farm(tmp_path, "r0001", "A", META)
    append_turns(d, [Turn(turn=1, role="assistant", phase="expand", iteration=1,
                          content="expanding"),
                     Turn(turn=2, role="assistant", phase="compress", iteration=1,
                          content="the compressed state")])
    assert next_turn_index(d) == 3
    assert last_compressed(d) == "the compressed state"

    entry = LedgerEntry(trigger="critique", change="qualified", novel_content=True)
    append_ledger(d, entry)
    assert read_ledger(d) == [entry]

    trigger = TriggerEmission(text="A storage glut falsifies this.", severity="high")
    append_triggers(d, [trigger])
    append_triggers(d, [trigger])
    assert read_triggers(d) == [trigger, trigger]


def test_critique_and_outcome_files(tmp_path):
    d = init_farm(tmp_path, "r0001", "A", META)
    report = CritiqueReport(findings=[CritiqueFinding(
        target_text="x", kind="warrant_probe", classification="undercutting",
        severity="med", text="The warrant assumes static demand.")],
        premortem="The thesis failed because demand shifted.", summary="one probe")
    path = write_critique(d, 1, report)
    assert path.name == "r01.json" and path.parent.name == "critiques"

    assert read_outcome(d) is None
    write_outcome(d, "CONCLUDE", None)
    assert read_outcome(d) == {"decision": "CONCLUDE", "died_because": None}


def test_empty_farm_dir_reads_are_safe(tmp_path):
    d = tmp_path / "farms" / "r0001" / "Z"
    d.mkdir(parents=True)
    assert read_turns(d) == [] and read_ledger(d) == [] and read_triggers(d) == []
    assert next_turn_index(d) == 0 and last_compressed(d) is None
