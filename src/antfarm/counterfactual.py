import random

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
