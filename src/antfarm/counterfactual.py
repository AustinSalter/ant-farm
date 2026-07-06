import random

from antfarm.emission import PersonaSwapOutput
from antfarm.transcript import Turn


def _renumber(turns: list[Turn]) -> list[Turn]:
    return [t.model_copy(update={"turn": i}) for i, t in enumerate(turns)]


def shuffle_turns(turns: list[Turn], seed: int) -> list[Turn]:
    shuffled = list(turns)
    random.Random(seed).shuffle(shuffled)
    return _renumber(shuffled)


def graft(host: list[Turn], donor: list[Turn], start_iteration: int) -> list[Turn]:
    kept = [t for t in host if t.iteration < start_iteration]
    spliced = [t for t in donor if t.iteration >= start_iteration]
    return _renumber(kept + spliced)


def swap_package(turns: list[Turn], start_iteration: int) -> dict:
    kept = [t.model_dump() for t in turns if t.iteration < start_iteration]
    regen = sorted({t.iteration for t in turns if t.iteration >= start_iteration})
    return {"eligible": bool(kept) and bool(regen), "context": kept,
            "regen_iterations": regen, "start_iteration": start_iteration}


def regenerated_to_turns(output: PersonaSwapOutput) -> list[Turn]:
    return [Turn(turn=i, role="assistant", phase=t.phase, iteration=t.iteration,
                 content=t.content)
            for i, t in enumerate(output.turns)]


def persona_swap(host: list[Turn], regenerated: list[Turn],
                 start_iteration: int) -> list[Turn]:
    kept = [t for t in host if t.iteration < start_iteration]
    # filter the regenerated side like graft() filters its donor: the swap agent
    # may echo a rewritten earlier-iteration context turn, which would duplicate
    # a kept host turn and break iteration monotonicity in the exported trace.
    spliced = [t for t in regenerated if t.iteration >= start_iteration]
    return _renumber(kept + spliced)
