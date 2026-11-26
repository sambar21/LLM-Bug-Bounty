"""Apply every attack to every fake report and write data/attacked/."""

import sys
from pathlib import Path

from triage.attacks import ATTACKS, choose_placement
from triage.schema import join_front_matter, split_front_matter

ROOT = Path(__file__).resolve().parent.parent
FAKES = ROOT / "data" / "fakes"
OUT_DIR = ROOT / "data" / "attacked"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.md"):
        stale.unlink()
    count = 0
    for path in sorted(FAKES.glob("*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        for name, inject in sorted(ATTACKS.items()):
            placement = choose_placement(meta["id"], name)
            attacked_meta = {
                "id": f"{meta['id']}-{name}",
                "source_id": meta["id"],
                "pattern": meta["pattern"],
                "expected_valid": "false",
                "attack": name,
                "placement": placement,
            }
            text = join_front_matter(attacked_meta, inject(body, placement))
            out = OUT_DIR / f"{attacked_meta['id']}.md"
            out.write_text(text, encoding="utf-8", newline="\n")
            count += 1
    print(f"wrote {count} attacked reports to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
