from antfarm.counterfactual import graft, shuffle_turns
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
