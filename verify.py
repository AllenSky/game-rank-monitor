"""Diff a published chart against Apple's own web chart.

Usage:  python3 verify.py [country] [genre]
        python3 verify.py tr puzzle

Apple's chart page renders roughly the first 25 positions server-side and lazy
loads the rest, so that is as deep as this can check. It is enough to catch a
wrong genre, a wrong storefront, or a stale feed.
"""
import json
import re
import sys
import urllib.request

from topgames.config import GENRES

SITE = "https://alkanaks56.github.io/top-games"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140 Safari/537.36")

country = (sys.argv[1] if len(sys.argv) > 1 else "us").lower()
genre = (sys.argv[2] if len(sys.argv) > 2 else "puzzle").lower()
if genre not in GENRES:
    sys.exit(f"unknown genre {genre!r}; try one of: {', '.join(sorted(GENRES))}")

ours = json.load(urllib.request.urlopen(
    f"{SITE}/{country}/{genre}/data/chart.json", timeout=30))["items"]

slug = genre.replace("_", "-") + "-games"
url = f"https://apps.apple.com/{country}/charts/iphone/{slug}/{GENRES[genre]}"
page = urllib.request.urlopen(
    urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30
).read().decode("utf-8", "replace")

seen, apple = set(), []
for n in re.findall(r'"name"\s*:\s*"([^"]{2,60})"', page):
    if n not in seen:
        seen.add(n)
        apple.append(n)

names = [i["name"] for i in ours]
try:
    apple = apple[apple.index(names[0]):]
except ValueError:
    sys.exit(f"our #1 ({names[0]!r}) does not appear on {url}")

depth = min(25, len(names), len(apple))
mine, theirs = names[:depth], apple[:depth]
same_pos = sum(1 for i in range(depth) if mine[i] == theirs[i])

# A chart reshuffles constantly. Our snapshot is fixed and Apple's page is live,
# so the honest question is whether the same apps are present, not whether the
# order is identical: a reorder is drift, a missing app is a bug.
missing = [n for n in mine if n not in theirs]
extra = [n for n in theirs if n not in mine]

print(f"{genre} / {country.upper()}  —  {url}")
print(f"  top {depth}: {same_pos} in the same position, "
      f"{depth - same_pos} moved")
print(f"  membership: {depth - len(missing)}/{depth} of ours also on Apple's page")
if missing:
    print("  in ours but not on Apple's page (a real difference):")
    for n in missing:
        print(f"    - {n}")
if extra:
    print("  on Apple's page but not in our top %d (likely newly climbed):" % depth)
    for n in extra:
        print(f"    + {n}")
if not missing and not extra:
    print("  same set of apps; any ordering difference is just chart drift "
          "between our snapshot and now.")
sys.exit(1 if missing else 0)
