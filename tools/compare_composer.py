"""Compare the composer's current text with the intended prompt, character by character."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dsh_chatgpt_bridge import core as sb  # noqa: E402

expected = Path(sys.argv[1]).read_text(encoding="utf-8").rstrip() if len(sys.argv) > 1 else ""
target = sb.locate_sidebar()
typed = sb.composer_text(target)

exp_norm = sb.normalize_for_compare(expected)
got_norm = sb.normalize_for_compare(typed)

print(f"raw composer chars   : {len(typed)}")
print(f"expected chars       : {len(expected)}")
print(f"normalised expected  : {len(exp_norm)}")
print(f"normalised composer  : {len(got_norm)}")
print(f"contained            : {exp_norm in got_norm}")

limit = min(len(exp_norm), len(got_norm))
first_diff = next((i for i in range(limit) if exp_norm[i] != got_norm[i]), None)
print(f"first differing index: {first_diff}")
if first_diff is not None:
    lo = max(0, first_diff - 60)
    print(f"  expected around it : ...{exp_norm[lo:first_diff + 60]!r}")
    print(f"  composer around it : ...{got_norm[lo:first_diff + 60]!r}")

print("\nexpected head:", repr(exp_norm[:120]))
print("composer head:", repr(got_norm[:120]))
print("expected tail:", repr(exp_norm[-120:]))
print("composer tail:", repr(got_norm[-120:]))
