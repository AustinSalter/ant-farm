from pathlib import Path

AGENTS = ["surveyor", "scout", "blind-critic", "hole-finder", "stitcher",
          "sentinel", "curator", "clerk"]
AGENTS_DIR = Path(__file__).parent.parent / ".claude" / "agents"


def _frontmatter(name: str) -> dict:
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{name}.md missing frontmatter"
    block = text.split("---", 2)[1]
    fields = {}
    for line in block.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_all_agents_exist_with_valid_frontmatter():
    for name in AGENTS:
        fields = _frontmatter(name)
        assert fields["name"] == name
        assert fields["description"]
        assert fields["tools"]


def test_blinding_rules_are_stated():
    critic = (AGENTS_DIR / "blind-critic.md").read_text(encoding="utf-8")
    assert "authorless" in critic or "third-party" in critic
    scout = (AGENTS_DIR / "scout.md").read_text(encoding="utf-8")
    assert "view" in scout and "well" in scout  # routing rule is written down


REFERENCES = ["expansion", "compression", "sublation-and-decision", "critique-probes"]
REFS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "survey" / "references"


def test_pass_reference_files_are_ported_not_stubbed():
    for name in REFERENCES:
        text = (REFS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert len(text.splitlines()) >= 60, f"{name}.md looks stubbed - port the source content"


def test_routers_point_at_their_pass_files():
    scout = (AGENTS_DIR / "scout.md").read_text(encoding="utf-8")
    for name in ("expansion", "compression", "sublation-and-decision"):
        assert f"references/{name}.md" in scout, f"scout.md must route to {name}.md"
    critic = (AGENTS_DIR / "blind-critic.md").read_text(encoding="utf-8")
    assert "references/critique-probes.md" in critic
