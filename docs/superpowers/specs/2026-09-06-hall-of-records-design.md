# BDFL Hall of Records: Design

Date: 2026-09-06
Status: design approved by the owner; implementation plan next
Repo: `btcookies/bdfl-trade-notifier`, branch `claude/bdfl-hall-of-fame-f29d9a`
Builds on: `2026-09-04-discord-notifier-design.md` (the notifier this service sits beside)

## 1. Goal

A Pro Football Reference style record of the Barbara Dodson Fantasy League's whole history on MyFantasyLeague (MFL): every player's career as a BDFL starter, every franchise's history, head-to-head series, a records book, rookie drafts with hindsight, a trade ledger with a running verdict, and a rule-based Hall of Fame. Published as a static site that rebuilds itself weekly, with a Tuesday recap and a season wrap posted to the league's Discord channel.

Constraints: $0 to run, no manual work after the first deploy, and no exposure of MFL franchise ids anywhere a league member can see.

## 2. Decisions made with the owner

| Topic | Decision |
|---|---|
| Surface | Static website first; Discord gets a weekly recap and a season wrap. Slash commands are a later spec. |
| Pages | Player pages, franchise pages (with head-to-head on the page), records book, Hall of Fame, draft history, trade ledger. No season pages; the home page lists champions by year. |
| Franchise identity | Aggregate by MFL franchise id, display only the current name, group the page body by the names the team has used. Ids never appear in HTML or URLs. |
| Ranking stat | Value over replacement: points minus a replacement-level baseline per position per week. Raw points are always shown beside it. |
| Hall of Fame | Rule-based and automatic, thresholds in config, with a watch list. A curated overlay can come later. |
| Discord | Both posts: a recap every completed week of the season and a wrap after the final. |
| Hosting | GitHub Actions and GitHub Pages. Raw MFL snapshots are committed to this repo as JSON. No new AWS resources. |
| Code location | Same repo, a second top-level package `hof/`, sharing the notifier's MFL and Discord clients. |
| Manager names | Optional mapping in config, empty by default, shown on the franchise page only when filled in. |

## 3. Verified facts about the MFL API

Checked on 2026-09-06 without logging in. Base URL and pacing are as in the notifier spec.

- The current league export's `history.league[]` lists 2016 through 2026. Every season from 2017 on is league 65522. The 2016 season is league **79873**, visible only in that entry's URL; requests for 2016 against 65522 return `Invalid league ID`.
- Franchise ids `0001` to `0012` are the same in every season. Names change (for example `Teenage Newton Ninja Turtles` became `A.J. Mudbone`). The public export carries no owner names.
- `TYPE=league` for a season gives `franchises.franchise[]` with `id`, `name`, `division`; `divisions`; `starters` (`count` 8, `position[]` with `name` and `limit` such as `1` or `2-4`); `startWeek`, `endWeek`, `lastRegularSeasonWeek` (13 in 2016 and 2020, 14 in 2026); `rosterSize`, `taxiSquad`, `injuredReserve`, `draftPlayerPool` = `Rookie`. It is a dynasty league.
- `TYPE=weeklyResults&W=n` gives `matchup[]` each with two `franchise` entries (`id`, `score`, `result` W/L/T, `isHome`, `starters`, `nonstarters`, `optimal`, `opt_pts`, and `player[]` with `id`, `status` starter/nonstarter, `score`, `shouldStart`) plus `regularSeason`. In playoff weeks, franchises without a game appear in a separate top-level `franchise[]` with the same lineup fields. Players who did not play (bye, inactive) have no `score` key even in completed weeks. About 21 KB per week. Available back to 2016.
- `TYPE=standings` (alias `leagueStandings`) gives per franchise `h2hwlt`, `h2hw`, `h2hl`, `h2ht`, `divwlt`, `pf`, `pa`, `pp` (potential points), `avgpf`, `avgpa`, `strk`.
- `TYPE=schedule` gives `weeklySchedule[]` for every week with `matchup[].franchise[]` (`id`, `score`, `result`, `isHome`). In 2020: 6 matchups in weeks 1 to 13, 2 in weeks 14 and 15, 1 in weeks 16 and 17.
- `TYPE=playoffBrackets` lists brackets; bracket 1 is `BDFL Championship`, 6 teams, starting week 14 (15 in 2025). `TYPE=playoffBracket&BRACKET_ID=1` gives `playoffRound[]` with `week` and `playoffGame[]` (`game_id`, `home`/`away` with `franchise_id`, `seed` or `winner_of_game`, `points`).
- `TYPE=draftResults` gives `draftUnit.draftPick[]` (`round`, `pick`, `franchise`, `player`, `timestamp`, `comments`) and `round1DraftOrder`, a comma-separated list of the franchises that made each round-one pick after trades (a franchise that acquired picks appears more than once). Pick `comments` carry lines such as `Pick traded from Suck My Ditka.` naming the franchises the pick passed through, oldest first. 48 picks in 2020 (4 rounds).
- `TYPE=transactions&TRANS_TYPE=*&DAYS=400` returns the whole season: 623 entries in 2020 across `IR`, `FREE_AGENT`, `TAXI`, `BBID_WAIVER`, `BBID_AUTO_PROCESS_WAIVERS`, `TRADE`, `LOCK_ALL_PLAYERS`, `UNLOCK_ALL_PLAYERS`. `FREE_AGENT` uses `transaction` = `"{added},|{dropped},"`; `IR` has `activated`/`deactivated`; `TAXI` has `promoted`/`demoted`.
- `LOCK_ALL_PLAYERS` fires once per week at the first Sunday kickoff (17:00 or 18:00 UTC); `UNLOCK_ALL_PLAYERS` fires Wednesday morning, and the final week of a season has no unlock. Week k of a season corresponds to the k-th lock in timestamp order.
- `TYPE=players&PLAYERS=a,b,c` works for past seasons and returns that season's `name`, `position`, `team`.
- `TYPE=nflSchedule` and `TYPE=calendar` return nothing useful without login; they are not used.
- The in-progress 2026 week 1 returns matchups with `result` T and no `score` at either the franchise or player level until games are played.

## 4. Architecture

One Python package, `hof`, with three commands run by one GitHub Actions workflow.

```
fetch   MFL ──▶ data/raw/<year>/*.json     (completed seasons never refetched)
build   data/raw ──▶ in-memory model ──▶ dist/   (static HTML, CSS, JS, search index)
notify  model + data/notify-state.json ──▶ Discord webhook   (recap or wrap, once per week)
```

- **fetch** discovers seasons from the current league export's `history`, applies per-season league id overrides from config, and pulls every export listed in section 5 for each season that is not marked complete. A season is complete once the run date is on or after February 1 of the following year; fetch then writes `meta.json` with `complete: true` and never touches that directory again. The current season is refetched in full every run (about 25 requests) so stat corrections flow through. Fetch writes into a temporary directory and swaps it in only after every request for that season succeeds.
- **build** loads every snapshot, computes the model of section 6, and renders the site of section 7 into an output directory. There is no database; eleven seasons are about 6 MB of JSON.
- **notify** decides whether a new week completed since the last post, builds the recap or wrap of section 8 from the same model, posts it, and updates the state file.

MFL access goes through the notifier's `MflClient`, which gains one public method, `export(year, type, **params)`, wrapping the existing private request path so pacing, throttling, and error mapping stay in one place. The 2016 season uses a second client instance constructed with league id 79873.

## 5. Snapshots and configuration

### Snapshot layout

```
data/
  config.toml
  notify-state.json
  raw/
    2020/
      meta.json              {"league_id": "65522", "complete": true, "fetched_at": "..."}
      league.json
      standings.json
      schedule.json
      playoffBrackets.json
      playoffBracket-1.json
      draftResults.json
      transactions.json      TRANS_TYPE=*, DAYS=400
      players.json           merged players export for every id referenced this season
      weeklyResults/
        W01.json ... W17.json   startWeek..endWeek from league.json
```

Files are the MFL response bodies as received, pretty-printed with sorted keys so weekly diffs of the current season are readable. `players.json` is the union of `PLAYERS=` requests in chunks of 200 ids, covering every id in the season's lineups, draft, and transactions.

### `data/config.toml`

```toml
[league]
id = "65522"
site_base_url = "https://btcookies.github.io/bdfl-trade-notifier/"

[seasons.overrides]
2016 = "79873"

[hall_of_fame]
player_min_vor = 400.0
player_min_starts = 30
franchise_min_titles = 2
watch_list_margin = 100.0

[[managers]]        # optional; omit entirely to hide the field
franchise = "0001"
name = "Example Name"
from = 2016
```

`tomllib` from the standard library reads it. Thresholds are reviewed against the backfill before the first deploy (section 13).

## 6. Stats model

All figures derive from the raw snapshots at build time. Scores are kept to one decimal, matching the league's `precision`.

### Identity

- **Franchise** = MFL franchise id. Displayed only by the name in the newest season's league export. Ids never appear in rendered HTML, URLs, or Discord text.
- **Era** = a maximal run of consecutive seasons in which the franchise's name matches after casefolding, trimming, and collapsing internal whitespace. A franchise page groups its season rows by era, newest first, with an era subtotal row.
- **Player** = MFL player id. Name, position, and NFL team are taken from the players snapshot of each season, so a player's position is per season. A player is included in the site if they have at least one counted start.
- **Manager** names come from config only.

### Games, starts, and lineups

- A **counted game** is a `weeklyResults` matchup in a week at or before `lastRegularSeasonWeek` (regular season), or a matchup in a playoff week whose two franchises appear together in a `playoffBracket-1` game for that week (playoff). Any other lineup in a playoff week (eliminated teams, consolation games) is not a game and produces no starts, records, or milestones.
- A **start** is a player in the `starters` list of a franchise in a counted game. Its points are the player's `score` for that week, or 0.0 when absent. Bench points are the same for the `nonstarters` list.
- **Lineup efficiency** for a game is `score / opt_pts`; **bench points left** is `opt_pts - score`.
- Win-loss-tie comes from `result`. Win percentage is `(W + 0.5 T) / games`.

### Value over replacement (VOR)

For each season, week, and position:

1. Pool = every player with `status` starter in every lineup MFL lists for that week, including lineups that are not counted games, with their position from that season's players snapshot. Players with no score count as 0.0.
2. `N` = number of franchises in that season times the position's minimum starters, taken from the first number of `starters.position[].limit` in that season's league export (QB 1, RB 2, WR 2, TE 1 → 12, 24, 24, 12 for twelve teams).
3. Baseline = the N-th highest score in the pool, or the lowest score when the pool has fewer than N entries.

A start is worth `points - baseline`. Season, career, playoff, franchise-stint, draft-pick, and trade totals are sums over counted starts. Every leaderboard and "top starter" cell sorts on VOR and displays raw points beside it.

### Player careers

- A **stint** is a maximal run of consecutive weeks (within and across seasons) in which the player appears in one franchise's `starters` or `nonstarters`. The tenure bar on the player page is the stint list.
- **Arrival and departure** are matched from the transaction log by player id and franchise: `DRAFT` from draft results (round and pick), `TRADE` (with the other side's assets), `BBID_WAIVER` (bid), `FREE_AGENT` add or drop. Unmatched boundaries show as "joined" or "left" with the week.
- Per-season row: franchise, starts, points, VOR, bench points, playoff starts and points, and a title marker.
- **Title as a starter** = in the `starters` list of the champion in the final game.
- Career totals: starts, points, VOR, bench points, playoff starts and points, titles, franchises played for.

### Franchises

- Per season: W-L-T, division record, PF, PA, seed, finish, top starter (by VOR, showing points).
- **Finish** labels: `Champion`, `Runner-up`, then `Lost <round>` where the last two rounds before the final are named `Semifinal` and `Final`, the first round played is `First Round` (never a team-count name like `Quarterfinal`, since BDFL's bracket has byes), and any round between those falls back to `Round <n>`; else `Missed playoffs`. The in-progress season shows `In progress`.
- All-time and per-era: record, PF, PA, playoff appearances, playoff record, titles, best and worst season (by win percentage, then points for), longest win and loss streaks, current streak (across seasons).
- All-time top starters: players ranked by VOR accumulated while starting for this franchise, with an era filter.
- **Head-to-head** against each opponent, listed by the opponent's current name: all-time, regular-season, and playoff records, PF, PA, average margin, current streak, last meeting, and the full game log with the names both teams used at the time.
- Draft picks with the player's points and VOR as a starter for this franchise; trades from the ledger involving this franchise.
- A franchises index page ranks every franchise by all-time win percentage.

### Records book

Top ten for each, over counted games, with playoff games flagged:

| Group | Records |
|---|---|
| Team, single game | most points, fewest points, biggest margin of victory, closest game, most points in a loss, fewest points in a win, most bench points left, highest-scoring final |
| Team, season | most points, fewest points, best record (win percentage, then points for), longest win streak, longest loss streak, most bench points left, best lineup efficiency |
| Player, single game | most points as a starter, highest VOR |
| Player, season | most points as a starter, highest VOR, most starts |
| Player, career | most points, highest VOR, most starts, most titles as a starter |

### Hall of Fame

Evaluated after each completed season in chronological order, so class years spread across history.

- A **player** is inducted in the first completed season at whose end career VOR ≥ `player_min_vor` and career starts ≥ `player_min_starts`. The plaque shows position, class year, franchises, starts, points, VOR, titles as a starter.
- A **franchise** is inducted in the season of its `franchise_min_titles`-th title. The plaque shows class year, titles, all-time record.
- The **watch list** shows players on a roster in the newest fetched week, not yet inducted, with career VOR ≥ `player_min_vor - watch_list_margin`, sorted by distance to the line.

### Draft hindsight

For each pick: player, drafting franchise, points and VOR as a starter for that franchise, and career points and VOR overall. Per draft: **steal** = highest VOR-for-drafting-franchise outside round one, **bust** = lowest in round one. The drafts index ranks franchises by summed VOR of all their picks.

### Trade ledger

For each `TRADE`: the two sides by the names they used at the time, the assets each received, and a verdict.

- A **player** received is credited with points and VOR as a starter for the receiving franchise in every week from the trade's effective week until the player's stint with that franchise ends. The effective week is the first week whose `LOCK_ALL_PLAYERS` timestamp is after the trade timestamp; a trade after the season's last lock takes effect in week 1 of the next season.
- A **future pick** (`FP_<franchise>_<year>_<round>`) resolves to a player when that year's draft snapshot has exactly one pick in that round whose original owner is the named franchise. The original owner of a pick is the first franchise named in the pick's `comments` lines of the form `Pick traded from <name>`, matched against that season's franchise names, or the drafting franchise when no such line exists. (MFL's `round1DraftOrder` lists post-trade owners, so it cannot identify original owners.) Otherwise it displays as the pick with no value. A **current-year pick** (`DP_<round>_<pick>`, both zero-based) resolves directly by round and pick.
- **Blind-bid dollars** display without a value.
- Verdict = difference in summed VOR, shown as "Ahead: <name> by <n>" or "Even".

### In-progress season

Everything counts immediately. Pages and the footer say `through <year> Week <n>` for the newest completed week. Hall of Fame induction is evaluated only for completed seasons; the watch list updates weekly.

## 7. Site

Static HTML rendered from Jinja2 templates, one hand-written stylesheet, and one small plain-JavaScript file for sorting tables, expanding head-to-head rows, and the player search. No framework, no bundler.

| Path | Page |
|---|---|
| `/` | Newest Hall of Fame class, champions and runners-up by year, top five career leaders by VOR, section links |
| `/players/` | Every player with a start: position, seasons, franchises, starts, points, VOR; sortable; search box filtering a JSON index (`players.json`, roughly 50 KB) |
| `/players/<slug>-<mfl-player-id>/` | Player page: header, tenure bar, per-season table, career totals, transaction story |
| `/franchises/` | Every franchise by all-time win percentage with titles and playoff record |
| `/franchises/<slug-of-current-name>/` | Franchise page as mocked: summary row, era-grouped seasons, top starters, playoff history, head-to-head, draft picks, trades |
| `/records/` | Records book |
| `/hall-of-fame/` | Plaques by class year, then the watch list and the rules in one sentence each |
| `/drafts/` and `/drafts/<year>/` | Franchise draft rankings; each draft with hindsight columns |
| `/trades/` | Every trade newest first with per-season anchors and verdicts |

Slugs are lowercase ASCII with hyphens. A renamed franchise moves to a new URL; nothing external links deeper than `/`. The player id suffix (an MFL player id, not a franchise id) keeps same-named players apart. All internal links are relative to `site_base_url` so the site works under the Pages project path. Tables wider than the viewport scroll horizontally inside their container. Every page's footer carries "through <year> Week <n>", "VOR: points above the last guaranteed starter at the position that week", and "Data from MyFantasyLeague".

Rendering is deterministic: the same snapshots produce byte-identical output, which keeps Pages deploys and tests stable.

## 8. Discord posts

Posted through the notifier's `DiscordWebhook` with its limits, `allowed_mentions` off, and no username override. The webhook URL comes from the `DISCORD_WEBHOOK_URL` environment variable, set from a repository secret.

### Week completion

Week k of the current season is complete when `now ≥ lock_k + 40 hours`, where `lock_k` is the k-th `LOCK_ALL_PLAYERS` timestamp in that season's transaction snapshot, and every counted matchup for the week has a franchise-level `score`. Sunday 17:00 UTC plus 40 hours is Tuesday 09:00 UTC, before the scheduled run. The **newest complete week** is the largest such k.

### State

`data/notify-state.json` holds `{"season": 2026, "week": 9, "kind": "recap"}` for the last post. Notify posts only when the newest complete week is later than the recorded one, then writes the new state. A manual re-run therefore never double-posts, and a failed post leaves the state unchanged.

### Weekly recap

One embed, title `📜 Week <n> in the record books`, color `0xF1C40F`.

- Description: over counted games, the week's highest team score and its franchise, and the top starter by VOR with points and franchise.
- Field `Records & milestones`, omitted when empty, one line each: every game or performance from this week that entered a records-book top ten (with its rank); every player who crossed a multiple of 500 career points as a starter or 100 career starts this week; every win that was the winner's first over that opponent ever, or first since at least two seasons ago.
- Field `Playoff picture` in regular-season weeks: the top six franchises in the standings export's order with records, then any franchise outside the six within one win of the sixth. In playoff weeks the field is `Bracket` instead: this week's bracket results and next week's matchups.
- Footer: `Full records: <site_base_url> · through Week <n>`.

### Season wrap

Sent instead of a recap when the newest complete week is the final's week. One embed, title `🏆 <year> season wrap`, color `0xE5B80B`.

- Description: champion, runner-up, final score, the champion's record and PF with its all-time rank when in the top ten seasons.
- Field `Season awards`: top starter (points), best VOR, best lineup manager (season efficiency), most bench points left.
- Field `🏛 Hall of Fame · Class of <year>`: each new inductee with key numbers, or `No new inductees`.
- Footer: `Full records: <site_base_url>`.

## 9. Workflow

`.github/workflows/hof.yml`, actions pinned to exact versions like the existing workflows.

- Triggers: `schedule: '0 11 * 9-12,1 2'` (Tuesdays 11:00 UTC, September through January), `push` to `main` touching `hof/**`, `data/**`, or the workflow file, and `workflow_dispatch`.
- Permissions: `contents: write`, `pages: write`, `id-token: write`. Concurrency group `hof` with no cancellation.
- Steps: checkout; Python 3.13; `pip install -r hof/requirements.txt`; `python -m hof fetch`; commit and push `data/raw` if changed as `github-actions[bot]`; `python -m hof build --out dist`; upload and deploy the Pages artifact; `python -m hof notify` when repository variable `HOF_NOTIFY` is `true`, with the secret in the environment; commit and push `data/notify-state.json` if changed.
- Pushes made with the workflow's built-in token do not trigger other workflows, so the weekly data commit never starts the notifier's deploy workflow or a second run of this one.
- The existing `ci.yml` runs the `hof` tests and ruff as part of the same job.

Owner setup: enable GitHub Pages with source "GitHub Actions", add the `DISCORD_WEBHOOK_URL` secret, and set `HOF_NOTIFY` to `true` once the site looks right.

## 10. Repository layout

```
hof/
  __init__.py
  __main__.py            # python -m hof {fetch,build,notify}
  config.py              # Config from data/config.toml
  fetch.py               # season discovery, snapshot fetching, temp-dir swap, meta.json
  snapshots.py           # load a season's raw files into typed Season objects
  model/
    season.py            # franchises, eras, weeks, counted games, lineups, bracket
    players.py           # player identity per season
    transactions.py      # typed transaction log, lock timestamps, effective weeks
  stats/
    vor.py               # baselines and per-start value
    careers.py           # stints, per-season rows, career totals, arrivals and departures
    franchises.py        # season rows, finishes, streaks, era subtotals, head-to-head
    records.py           # records book
    hall.py              # induction and watch list
    drafts.py            # hindsight, steals and busts, franchise rankings
    trades.py            # ledger, pick resolution, verdicts
    milestones.py        # weekly recap inputs: new top-tens, milestones, series firsts, playoff picture
  site/
    build.py             # render everything into an output directory
    slugs.py
    templates/*.html
    static/site.css, site.js
  discord/
    recap.py             # weekly recap embed
    wrap.py              # season wrap embed
    notify.py            # completion rule, state file, posting
  requirements.txt       # jinja2, requests
data/                    # section 5
tests/hof/               # mirrors the package; fixtures/ holds real MFL responses and the synthetic league
.github/workflows/hof.yml
src/bdfl/mfl.py          # + export()
pyproject.toml           # pythonpath gains "."; ruff covers hof
requirements-dev.txt     # + -r hof/requirements.txt
```

## 11. Testing

Unit tests with pytest on Python 3.13, no network.

- **snapshots and model**: parse real 2020 responses (league, one regular-season week, one playoff week, standings, schedule, bracket, draft, transactions, players) captured as fixtures; assert counted games, lineups, lock timestamps, dict-versus-list normalization, and missing scores read as 0.0.
- **stats**: a synthetic four-franchise, three-season league with hand-computed expectations for baselines and VOR, stints across a trade, eras and subtotals, streaks across seasons, head-to-head splits, records-book entries, milestone detection, series firsts, pick resolution, trade attribution by effective week, induction class years, and the watch list.
- **site**: build the synthetic league into a temporary directory; assert every expected path exists, key strings appear on each page type, links resolve to generated files, output is byte-identical across two builds, and no franchise id string appears in any HTML file.
- **discord**: golden embed dictionaries for a recap with and without milestones and for a wrap; the completion rule at the 40-hour boundary; the state file suppressing a duplicate post and surviving a failed post.
- **fetch**: stubbed HTTP; the temp-dir swap on failure, completed seasons skipped, the 2016 league id override, players chunking at 200 ids.
- Ruff with the existing configuration extended to `hof`.

## 12. Failure handling

- **Fetch**: any MFL error, including 429, aborts the run before the season directory is replaced; nothing partial is committed. The next scheduled run retries. There is no in-run retry, per MFL guidance.
- **Build** never fails on content. An id absent from the players snapshot renders as `Unknown player`; a bracket game without a matching matchup is skipped; an unparsable transaction is logged and ignored. Warnings appear in the workflow log.
- **Notify**: a Discord error fails the step, leaves the state file unchanged, and GitHub's failed-workflow email to the owner is the alert. The next run posts the newest complete week only, so at most one recap is ever skipped.
- **Pages**: a failed deploy leaves the previous site live.

## 13. Rollout

1. Implement the package and tests. Run `python -m hof fetch` locally to backfill 2016 through 2025 and 2026 to date; commit the snapshots.
2. Run `python -m hof build` locally, print the inaugural Hall of Fame classes, watch list, and records-book tops, and tune `config.toml` thresholds with the owner until the inaugural class looks right.
3. Owner enables GitHub Pages (source: GitHub Actions) and adds the `DISCORD_WEBHOOK_URL` secret.
4. Merge; the workflow deploys the site. Owner reviews it.
5. Owner sets `HOF_NOTIFY` to `true`; the next Tuesday run posts the first recap.

## 14. Out of scope

- Discord slash commands (needs a Discord application and an interactions endpoint).
- A curated Hall of Fame overlay or league voting.
- Season pages, division standings pages, custom domain, dark theme.
- Consolation games and non-bracket playoff-week matchups.
- Reading the notifier's DynamoDB table; the MFL transaction export is the source for trades here too.
