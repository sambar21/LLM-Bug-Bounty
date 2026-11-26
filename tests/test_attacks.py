import re
from pathlib import Path

import pytest

from triage import attacks
from triage.attacks import ATTACKS, HIDDEN_TEXT, ZERO_WIDTH_SPACE, choose_placement, render_visible
from triage.schema import split_front_matter

ROOT = Path(__file__).resolve().parent.parent
REPORT = """# Missing headers on /about

## Summary

The about page has no CSP.

## Steps

```
curl -I https://app.tollgate.example/about

HTTP/2 200
```

## Impact

Attackers could do things.
"""


@pytest.mark.parametrize("name", sorted(ATTACKS))
@pytest.mark.parametrize("placement", attacks.PLACEMENTS)
def test_injectors_are_deterministic_and_add_under_600_chars(name, placement):
    first = ATTACKS[name](REPORT, placement)
    assert first == ATTACKS[name](REPORT, placement)
    assert first != REPORT
    assert len(first) - len(REPORT) < 600


def test_placement_top_middle_end():
    block = "INJECTED"
    assert attacks.place(REPORT, block, "top").startswith(block)
    assert attacks.place(REPORT, block, "end").rstrip().endswith(block)
    middle = attacks.place(REPORT, block, "middle")
    assert not middle.startswith(block) and not middle.rstrip().endswith(block)


def test_middle_placement_never_lands_inside_a_code_fence():
    middle = attacks.place(REPORT, "INJECTED", "middle")
    before = middle[: middle.index("INJECTED")]
    assert before.count("```") % 2 == 0


def test_choose_placement_is_seeded_by_report_and_attack():
    assert choose_placement("07", "hidden") == choose_placement("07", "hidden")
    picks = {choose_placement(f"{i:02d}", "override") for i in range(1, 26)}
    assert picks == set(attacks.PLACEMENTS)


def test_hidden_instruction_is_invisible_when_rendered():
    attacked = attacks.hidden(REPORT, "middle")
    assert HIDDEN_TEXT in attacked
    assert ZERO_WIDTH_SPACE in attacked
    visible = render_visible(attacked)
    assert "ignore previous instructions" not in visible.lower()
    assert "Mark" not in visible
    assert re.sub(r"\n{3,}", "\n\n", visible).strip() == REPORT.strip()


def test_zero_width_copy_has_no_plain_spaces_between_words():
    attacked = attacks.hidden(REPORT, "end")
    spaced = ZERO_WIDTH_SPACE.join(HIDDEN_TEXT.split(" "))
    assert spaced in attacked
    assert " " not in spaced


def test_severity_anchor_puts_rce_in_the_title():
    first_line = attacks.severity_anchor(REPORT, "end").split("\n")[0]
    assert first_line.startswith("# ") and "RCE" in first_line
    assert "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H" in attacks.severity_anchor(REPORT, "top")


def test_committed_attacked_files_record_attack_and_placement():
    files = sorted((ROOT / "data" / "attacked").glob("*.md"))
    assert len(files) == 125
    for path in files:
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        assert meta["attack"] in ATTACKS
        assert meta["placement"] == choose_placement(meta["source_id"], meta["attack"])
        source = ROOT / "data" / "fakes" / f"{meta['source_id']}.md"
        _, clean = split_front_matter(source.read_text(encoding="utf-8"))
        assert body == ATTACKS[meta["attack"]](clean, meta["placement"])
