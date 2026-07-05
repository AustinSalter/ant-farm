from antfarm.counterfactual import (
    graft,
    persona_swap,
    regenerated_to_turns,
    shuffle_turns,
    swap_package,
)
from antfarm.emission import PersonaSwapOutput, RegeneratedTurn
from antfarm.transcript import Turn


def _turns(prefix, n_iterations=3, per_iteration=2):
    turns, i = [], 0
    for it in range(1, n_iterations + 1):
        for k in range(per_iteration):
            turns.append(Turn(turn=i, role="assistant", phase="expand", iteration=it,
                              content=f"{prefix} iteration {it} step {k}"))
            i += 1
    return turns


def test_shuffle_is_deterministic_and_renumbered():
    turns = _turns("host")
    a = shuffle_turns(turns, seed=7)
    b = shuffle_turns(turns, seed=7)
    assert [t.content for t in a] == [t.content for t in b]  # deterministic
    assert [t.turn for t in a] == list(range(6))             # renumbered
    assert sorted(t.content for t in a) == sorted(t.content for t in turns)  # same multiset
    # seed 7 is verified non-identity on these 6 turns; if the fixture changes and
    # this fires, pick a different seed - the assertion is the guard
    assert [t.content for t in a] != [t.content for t in turns]  # actually permuted
    assert [t.content for t in turns] == [f"host iteration {it} step {k}"
                                          for it in (1, 2, 3) for k in (0, 1)]  # input untouched


def test_graft_splices_at_iteration_boundary():
    host, donor = _turns("host"), _turns("donor")
    grafted = graft(host, donor, start_iteration=3)
    assert [t.content for t in grafted] == [
        "host iteration 1 step 0", "host iteration 1 step 1",
        "host iteration 2 step 0", "host iteration 2 step 1",
        "donor iteration 3 step 0", "donor iteration 3 step 1",
    ]
    assert [t.turn for t in grafted] == list(range(6))


def test_swap_package_splits_at_iteration_boundary():
    turns = _turns("host")
    pkg = swap_package(turns, start_iteration=2)
    assert pkg["eligible"] is True
    assert [t["iteration"] for t in pkg["context"]] == [1, 1]
    assert pkg["regen_iterations"] == [2, 3]


def test_swap_package_ineligible_without_both_sides():
    turns = _turns("host", n_iterations=1)
    assert swap_package(turns, start_iteration=2)["eligible"] is False
    assert swap_package(turns, start_iteration=1)["eligible"] is False


def test_persona_swap_splices_regenerated_turns():
    host = _turns("host")
    regen = regenerated_to_turns(PersonaSwapOutput(turns=[
        RegeneratedTurn(phase="expand", iteration=2, content="alt persona expand"),
        RegeneratedTurn(phase="compress", iteration=2, content="alt persona compress"),
    ]))
    swapped = persona_swap(host, regen, start_iteration=2)
    assert [t.content for t in swapped] == [
        "host iteration 1 step 0", "host iteration 1 step 1",
        "alt persona expand", "alt persona compress",
    ]
    assert [t.turn for t in swapped] == list(range(4))
    assert all(t.role == "assistant" for t in regen)
