# QA checklist

Live site: <https://alkanaks56.github.io/top-games/>

Work top to bottom. Each item says what to do and what "correct" looks like, so a
failure is unambiguous rather than a judgement call.

---

## 1. Landing

- [ ] Opening the site shows the **Puzzle · US chart straight away** — no menu, no
      landing page, no chart picker to get past.
- [ ] The filter bar reads: **Country · Genre · Sort · Publisher · Rating · Released**.
- [ ] Header shows `synced HH:MM (Nm ago)` in **your** local time, not UTC. Hover it —
      the tooltip should name `Europe/Istanbul` and give the UTC value.

## 2. Country and genre behave like filters

- [ ] Change **Genre** to Racing. The page must update **in place** — no reload, no
      flash — the heading becomes "Racing, United States", and the address bar becomes
      `/us/racing/`.
- [ ] Change **Country** to Türkiye. Heading becomes "Racing, Türkiye". Ratings should
      differ from the US ones (storefronts rate independently).
- [ ] Genre dropdown lists **17 genres**, all capitalised, with `Role Playing` spelled
      as two words.
- [ ] Country dropdown lists **6**: US, GB, DE, TR, JP, BR.
- [ ] Switch genre/country **five or six times in a row.** This is where it broke
      before — a stale base URL made later switches silently load the wrong data.
      Every switch must show data matching the heading.

## 3. Secondary charts hide what they cannot know

Only **Puzzle · US** keeps history. On any other chart:

- [ ] There is **no Δ column** and **no Rank trend column**.
- [ ] The **Movers** tab is gone.
- [ ] The view toggle offers **Table and Grid only** — no Timeline.
- [ ] Back on Puzzle · US, all four reappear.

## 4. New releases

- [ ] The tab shows **one** genre control, not two. Controls are **Store · Released ·
      Genre · search**.
- [ ] **Store** defaults to the chart's country; **Genre** defaults to the chart's
      genre; **Released** defaults to "Last 30 days".
- [ ] Change **Store** to JP. The list must actually change — Japanese titles, a
      different count. While it loads the controls stay visible and disabled with a
      spinner. *(This is the bug from your screen recording — check it properly.)*
- [ ] Cycle Store through all six. Each shows a different count.
- [ ] Set **Released** to **Any time**. The count should jump into the **thousands**.
- [ ] With thousands loaded, paging and the 10/50/100 Rows control must stay
      responsive.
- [ ] Set **Genre** to "All genres" and confirm non-puzzle games appear.
- [ ] Games already in the chart carry a green **top 100** tag.

## 5. Data accuracy

```bash
python3 verify.py us puzzle
```

```bash
python3 verify.py tr strategy
```

- [ ] **membership** should be 25/25. A missing app is a real bug — report it.
- [ ] **position** differences are fine: our snapshot is fixed, Apple's page is live,
      and charts reshuffle hourly.
- [ ] Spot-check by eye against
      `https://apps.apple.com/us/charts/iphone/puzzle-games/7012` (swap country and
      genre in the URL).

## 6. Slack

- [ ] `python3 -m topgames digest daily --dry-run` prints blocks without sending.
- [ ] **Share to Slack** on Top 100 / Movers / New Releases posts to your channel.
      Pressing it twice within a minute is refused on purpose — that is the cooldown.
- [ ] The scheduled digest arrives at **09:00 Istanbul**. Only Puzzle · US posts;
      other charts are on-demand by design.

## 7. Known limits — not bugs

- **New releases are a sample, not a census.** Apple publishes no endpoint listing
  every release, so they are discovered by search sweeps. Expect a good sample, not
  every game that launched.
- **Some sweep terms fail on non-US storefronts.** Apple returns 403 under load, e.g.
  `jp/puzzle` while `jp/game` succeeds. Those storefronts pool fewer games as a
  result.
- **Dice and Educational are absent.** Apple's feed returns zero entries for both in
  every storefront.
- **`/top100` needs its Request URL set** in your Slack app before it works. The
  endpoint is live and allowlisted; the Slack-side config is not done.
- **The primary database is committed to git** and grows roughly 1 GB/year toward
  GitHub's 5 GB limit. Known, unaddressed, fix documented in the plan file.

## Reporting a failure

Include the URL you were on, the filter values, and the browser console output
(⌥⌘I → Console). The console is where the earlier fetch bugs were visible.
