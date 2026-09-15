# BDFL Analytics Layer and Mobile Rework: Design

Date: 2026-09-08
Status: design approved by the owner; implementation plan next
Repo: `btcookies/bdfl-trade-notifier`, branch `claude/fantasy-league-enhancements-3e1e60`
Builds on: `2026-09-06-hall-of-records-design.md` (the site and posts this extends)
Research: `docs/superpowers/research/2026-09-08-community-feature-research.md`

## 1. Goal

Add the analytics that other leagues' tools converge on most, computed from data the Hall of Records already loads: weekly awards, all-play records and luck, formula power rankings, and an all-time rivalry grid. Surface them on new season pages, on the franchise pages, in the records book, and as a second embed in the Tuesday Discord post. At the same time, make the existing site usable on a phone: keep the key numbers visible, never let the page scroll sideways, and rebuild the head-to-head block that breaks at phone width.

Constraints stay as before: $0 to run, no manual work after deploy, no franchise ids in anything a league member sees, deterministic output.

## 2. Decisions made with the owner

| Topic | Decision |
|---|---|
| Home for per-season stats | Season pages, one per year, the newest being the season in progress; plus all-play and luck columns on franchise season rows. |
| Awards | Nine fixed awards with plain default labels; any label can be renamed in `config.toml`. |
| Power rankings | A transparent composite of all-play percentage, win percentage, and recent form, with components shown. |
| Discord | Two embeds in the Tuesday message: the existing recap unchanged, then awards and power rankings. The wrap gains four lines. |
| Mobile | Column priority classes, a sticky key column, a scroll hint, and a reflowed head-to-head block. No card layouts. |
| Rivalries | A 12 by 12 grid page under the franchises section, linked from the franchises index and each franchise page, not from the nav. |

## 3. The numbers

All figures derive from the raw snapshots at build time, over counted games as defined in the Hall of Records design. Scores keep one decimal.

### All-play and luck

For each regular-season week of a season, every franchise with a counted game is compared against every other such franchise's score that week: a win for each it outscored, a tie for each it matched, a loss for each that outscored it. With 12 franchises playing, a week's all-play record is out of 11.

- **Expected wins** for a week = (all-play wins + 0.5 × all-play ties) / (franchises compared − 1).
- **Season all-play** = the sums of weekly all-play wins, losses, and ties; **all-play percentage** = (wins + 0.5 × ties) / (wins + losses + ties).
- **Season expected wins** = the sum of weekly expected wins over weeks played.
- **Luck** = (actual regular-season wins + 0.5 × ties) − season expected wins, shown with a sign to one decimal.

Playoff weeks are excluded because not every franchise plays a counted game. A week in which fewer than two franchises have a counted score produces no all-play rows.

### Power rankings

Computed after each regular-season week that has counted games, over the season to date:

```
score = 0.5 × all-play percentage (season to date)
      + 0.3 × win percentage (season to date, ties count half)
      + 0.2 × form
form  = all-play percentage over the last three regular-season weeks (their all-play wins, losses, and ties pooled, not weekly percentages averaged), or fewer while the season is younger
```

Rank by score descending, then points for descending, then current name. **Movement** = the previous ranked week's rank minus this week's rank; there is no previous rank in the first ranked week. The last regular-season ranking stands through the playoffs; nothing is recomputed in playoff weeks. Score displays to three decimals; components as percentages to one decimal.

### Weekly awards

Computed for every week with at least one counted game, over counted games only, so a playoff week awards only bracket games. Each award has a key, a default label, a holder, a value with a unit, and a one-line detail.

| Key | Default label | Holder | Value | Detail |
|---|---|---|---|---|
| `high_score` | Highest score | Franchise | Score | Opponent and result |
| `low_score` | Lowest score | Franchise | Score | Opponent and result |
| `blowout` | Biggest blowout | Winning franchise | Margin | "over <loser>, <score>–<score>" |
| `closest` | Closest game | Winning franchise, or the home franchise of a tie | Margin | "over <loser>, <score>–<score>" or "tied with <opponent>" |
| `best_lineup` | Best lineup | Franchise | Score ÷ optimal, as a percentage | "<score> of <optimal> possible" |
| `worst_lineup` | Most points left on the bench | Franchise | Optimal − score | "<score> of <optimal> possible" |
| `lucky_win` | Luckiest win | The winner with the lowest score | Score | "would have gone <w>-<l>-<t> against the field" |
| `unlucky_loss` | Unluckiest loss | The loser with the highest score | Score | "would have gone <w>-<l>-<t> against the field" |
| `best_benched` | Best player on a bench | Player | Points | "on <franchise>'s bench" |

Rules:

- An award is omitted when it has no candidate: no `lucky_win` or `unlucky_loss` without a decided game, no `best_lineup` or `worst_lineup` without optimal points, no `best_benched` without a scored non-starter, and no `lucky_win`/`unlucky_loss` all-play detail in a playoff week (the detail is dropped, the award remains).
- Ties break on the holder's score that week (higher first), then on the holder's name, so output is deterministic.
- Labels can be overridden in `config.toml`:

  ```toml
  [awards]
  low_score = "Golden Goose Egg"
  worst_lineup = "Armchair Quarterback"
  ```

  A key that is not one of the nine fails config loading with a message naming it.
- The **season tally** counts, per franchise, how many awards of each key it holds across the season's weeks. The **awards leader** is the franchise with the most awards of any kind; ties are listed together.

### Season additions

- The season wrap's "Season awards" field gains: awards leader with its count; luckiest franchise with its luck; unluckiest franchise with its luck; the final power ranking's number one with its score.
- The records book gains three "Team, season" tables, over finished seasons only like the existing season tables: `luck_high` "Luckiest season" (highest luck, unit `wins`, one decimal), `luck_low` "Unluckiest season" (lowest luck), and `allplay_best` "Best all-play record, season" (highest all-play percentage, unit `pct`, detail shows the all-play W-L-T). The `_format`/`mark` helpers gain the `wins` unit (one decimal, signed).

### Data model

New modules under `hof/stats/`:

- `allplay.py`: `AllPlayWeek(franchise_id, week, wins, losses, ties, expected_wins)` per franchise and week; `StandingLine(franchise_id, name, wins, losses, ties, points_for, points_against, allplay: tuple[int, int, int], allplay_pct, expected_wins, luck)` for a season through a given week, in MFL's standings order for that season, falling back to win percentage then points for then name when the standings export is absent.
- `power.py`: `PowerLine(rank, franchise_id, name, score, allplay_pct, win_pct, form, previous_rank | None)` with `movement` derived; `rankings(league, season, through_week)`.
- `awards.py`: `Award(key, label, holder_id, holder_name, franchise_id, value, unit, detail)`; `week_awards(league, season, week, labels)`; `tally(...)`.
- `analytics.py`: `WeekAnalytics(week, playoff, standings, power, awards)` and `SeasonAnalytics(year, weeks, tally, leaders)` where `leaders` holds the awards leader(s), luckiest, and unluckiest; `compute(league, labels) -> dict[int, SeasonAnalytics]`.
- `rivalries.py`: `RivalryGrid(order: tuple[franchise ids], cells: dict[(row id, col id), (wins, losses, ties)])` and three pair lists (most meetings; most lopsided and most even among pairs with at least five meetings), derived from the franchise histories.

`Model` gains `analytics: dict[int, SeasonAnalytics]` and `rivalries: RivalryGrid`. `compute()` in `hof/stats/model.py` calls the new modules; `Config` gains an `award_labels` mapping beside `hall_rules`, read from the `[awards]` table, validated at load.

## 4. Site

### Season pages

New section `/seasons/`, in the nav between Franchises and Records.

- **Index** `/seasons/`: every season newest first with year, champion, runner-up, best regular-season record (ties by points for), most regular-season points, luckiest franchise (ties by name), and awards leader (ties listed together). The year links to the season page; names link to franchise pages.
- **Season** `/seasons/<year>/`:
  1. Header: the year, then "Final" when the season has a decided final, else "through Week n". The champion sentence when decided.
  2. **Standings**: franchise (name used that year, linked), W-L-T, PF, PA, All-play W-L-T, AP%, xW, Luck. Sortable.
  3. **Power rankings** for the newest ranked week: #, Move, Franchise, Score, AP%, Win%, Form. One sentence beneath: "Score = 0.5 × all-play % + 0.3 × win % + 0.2 × form, where form is all-play % over the last three weeks." Omitted before the first ranked week.
  4. **Weekly awards**, newest week first, each week a compact list of label, holder, value, and detail; then the **tally** table: Franchise, Total, then one column per award in the table order above.
- Past seasons render from the same template, so 2016 onward get retroactive standings, luck, final rankings, and awards.

### Rivalries page

`/franchises/rivalries/`, linked from the franchises index (one line above its table) and from each franchise page's head-to-head heading.

- A 12 by 12 grid. Rows and columns share the franchises index order (all-time win percentage). Row header: current name; column header: the row number 1 to 12. Cell: the row franchise's all-time record against the column franchise, as "W-L" or "W-L-T" when ties exist, tinted from green (high win percentage) to red (low) with a neutral middle, linking to the row franchise's head-to-head section (`#h2h`). The diagonal is blank. A blank cell also appears for a pair that has never met.
- Beneath the grid, three lists of up to five pairs each: most meetings; most lopsided (largest gap from .500, at least five meetings); most even (closest to .500, at least five meetings). Each line names both franchises with links and the series record.

### Franchise pages

- Season rows gain **All-play** (W-L-T) and **Luck** columns; era subtotal rows sum both.
- The stats panel gains **All-play** (all-time percentage) and **Luck** (all-time sum, signed).
- One line under the panel: "Weekly awards: n · <label> k, <label> k, …" with non-zero labels only, linking to the seasons index. Omitted when the franchise has none.
- The head-to-head heading gains a "Rivalry grid" link and the section gets `id="h2h"`.

### Home page

- The champions table's year links to that season's page, and the Champion column is left-aligned (it is a name).
- Above it, one line when the newest season is not complete and has at least one counted game: "<year> · through Week n · standings, power rankings, and awards" linking to the season page.

### Records book

The three new season tables render in the existing "Team, season" group with no template change.

### Build

Templates `seasons.html`, `season.html`, `rivalries.html`; renderers `render_seasons` and `render_rivalries` appended to `RENDERERS`; `SECTIONS` gains `seasons`; `Site.url` gains kinds `season` (year) and `rivalries`. Rendering stays byte-identical across builds.

## 5. Discord

### Tuesday message

`build_embed` becomes `build_embeds(model, decision, site_url) -> list[dict]`. For a recap it returns the existing recap embed unchanged, followed by:

- Title `🏅 Week <n> awards and power rankings`, color `0x3498DB`. In a playoff week the title is `🏅 Week <n> awards` and the rankings field is omitted.
- Field `Awards`: one line per award in table order, `**<label>:** <holder>, <value> (<detail>)`. Values format by unit: points to one decimal, percentages to one decimal with `%`, margins to one decimal.
- Field `Power rankings`: twelve lines `<rank>. <move> <franchise> · <score>`, where move is `▲n`, `▼n`, `–` for no change, or `new` in the first ranked week.
- Footer: `Season page: <site_base_url>seasons/<year>/`.

Both fields use `fit_lines`. The message goes through the existing webhook client, whose 6,000-character check covers the whole message; awards and rankings together run about 1,300 characters. The dry run prints the list. State handling, the completion rule, and `decide()` do not change.

### Season wrap

`awards_lines` appends, after the existing four lines: `**Awards leader:** <names>, <n> awards`; `**Luckiest:** <franchise>, <luck>`; `**Unluckiest:** <franchise>, <luck>`; `**Final power ranking:** #1 <franchise>, <score>`. Each is omitted when its input is missing (for example a season with no regular-season games).

## 6. Mobile

All changes are in `site.css` and template class attributes. No JavaScript is added.

### Column priority

Cells carry `p2` or `p3`. `p3` hides below 720 px; `p2` hides below 480 px. Assignments:

| Table | Keep on phones | `p2` (hidden < 480) | `p3` (hidden < 720) |
|---|---|---|---|
| Home champions | Year, Champion, Runner-up | | |
| Players index | Player, Pos, GS, Pts, VOR | Titles | Years, Franchises, Active |
| Player season rows | Year, Franchise, GS, Pts, VOR | Bench, Title | PO GS, PO Pts |
| Franchises index | Franchise, Record, Titles | Pct, PO record | PF, PA, Playoffs, Streak |
| Franchise season rows | Year, W-L-T, PF, Finish, Luck | PA, All-play | Div, Seed, Top starter |
| Franchise top starters | #, Player, Pos, Pts, VOR | GS | Yrs |
| Franchise playoff history | Year, Opponent, Score, Res | | Round |
| Head-to-head meetings | Year, Wk, Opponent, Score, Res | | Round, As |
| Franchise draft picks | Year, Pick, Player, Pts, VOR | | |
| Franchise trades | With, Got, Gave | Verdict | Date |
| Records | #, Holder, Mark | Detail | |
| Hall watch list | Player, Pos, VOR, Needs | | GS |
| Drafts index (franchises) | Franchise, Picks, VOR from picks | | |
| Drafts index (years) | Year, Steal, Bust | | Rounds |
| Draft page | Pick, Team, Player, Pos, Pts, VOR | Career pts, Career VOR | Via, GS |
| Seasons index | Year, Champion | Runner-up | Best record, Most points, Luckiest, Awards leader |
| Season standings | Franchise, W-L-T, PF, Luck | PA, All-play | AP%, xW |
| Power rankings | #, Move, Franchise, Score | | AP%, Win%, Form |
| Awards tally | Franchise, Total | | every per-award column |
| Rivalry grid | everything (scrolls) | | |

### Sticky key column

The name cell in each scrolling table carries `key` and sticks to the left edge with an opaque background. When a narrow rank or year column precedes it, that column carries `rank` with a fixed width so the key cell sticks beside it (`left` equal to that width). Tables without a `key` cell scroll normally.

### Scroll hint

`.table-wrap` gets the pure-CSS scrolling-shadows treatment (layered background images with `background-attachment: local, scroll`) so a shadow appears at the right edge only when more columns exist beyond it.

### Head-to-head

- Below 720 px the summary row switches from the nine-column grid to a wrapped flex layout: opponent and all-time record on the first line, then the remaining figures as small "label value" pairs with the label from `data-label` rendered via `::before`. The header row is hidden.
- Every expanded meetings table is wrapped in `.table-wrap`, so opening a series never widens the page.

### Touch targets and polish

Row and summary padding grows to 8 px vertical below 720 px. The nav keeps wrapping as it does now.

### Acceptance check

At a 375 px viewport, no page may be wider than its viewport: `document.documentElement.scrollWidth <= document.documentElement.clientWidth`. The implementation plan includes a scripted browser pass over the local preview covering: home, players, one player, franchises, one franchise with a series expanded, rivalries, seasons, one season, records, hall of fame, drafts, one draft, trades.

## 7. Testing

pytest, no network, extending the synthetic four-franchise league in `tests/hof/`.

- **All-play and luck**: hand-computed weekly and season values, a tied game, a season in progress, a week with one counted score (no rows), playoff weeks excluded.
- **Power rankings**: components and composite, tie-break on points for, movement between weeks, `new` in the first ranked week, form over one and two weeks, no recomputation in playoff weeks.
- **Awards**: each key from a hand-built week; the omission rules; deterministic tie-breaking; label overrides and rejection of an unknown key; the tally and the leader with a tie.
- **Records**: the three new tables, finished seasons only, the `wins` unit formatting.
- **Rivalries**: grid cells and the three pair lists, including the five-meeting minimum.
- **Site**: seasons index, a season page, and the rivalries page exist and carry expected strings; franchise page shows the new columns, panel entries, and awards line; the home in-progress line appears only when a season is in progress; every `.h2h details table` is inside a `.table-wrap`; the priority classes are present on the listed tables (spot-check one per template); output byte-identical across two builds; no franchise id in any HTML.
- **Discord**: golden embeds for the second recap embed in a regular-season week and a playoff week; the wrap's new lines and their omission; the two-embed message under the character budget; the dry run printing a list.

## 8. Rollout

No workflow, secret, or required config changes. Award label overrides are optional. Implementation is expected as three plans: stats and records; site pages and mobile; Discord. After merge, the site rebuilds with every past season's page; the next Tuesday run posts the two-embed recap. The 375 px width check runs on the local preview before merge.

## 9. Out of scope

Slash commands, playoff odds, a Thursday preview, the bracket on season pages, card layouts on phones, dark theme, and anything needing an MFL login (future draft picks, live scoring).
