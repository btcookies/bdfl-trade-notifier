# What other leagues ask for: community feature research

Date: 2026-09-08
Purpose: candidate enhancements for the BDFL notifier, Hall of Records site, and Discord posts, ranked by how many independent communities, products, and open-source builders converge on each one. Input to a prioritization conversation with the owner and the league; not a design.

## How this was gathered, and what it could not reach

Five parallel research passes on 2026-09-08 covered: hobbyist and commercial league-history products; fantasy Discord/GroupMe/Slack bots and their issue trackers; open-source league-stats projects on GitHub, PyPI, and CRAN; AI-written league content; and engagement rituals (awards, punishments, constitutions, offseason activity).

Reddit was unreachable from every tool available (search, fetch, and the in-app browser are all blocked at the policy level for reddit.com), so r/DynastyFF, r/fantasyfootball, and r/FFCommish threads are not cited. The proxy used instead is convergence: when several unrelated builders and products each independently ship the same feature, or users file the same request in several issue trackers, that is treated as demand. Evidence counts below are counts of independent sources, not upvotes.

Two MFL feasibility checks were run against the public export API without login: `draftResults`, `players&DETAILS=1` (includes `birthdate`, `draft_year`, `draft_round`), and `injuries` return data; `futureDraftPicks`, `liveScoring`, and `assets` redirect to login (HTTP 302) and would need an MFL API key stored as a secret.

## What the market says about what is already built

- **Records book, franchise pages, head-to-head**: table stakes. Every league-history product leads with these (League Legacy, League Tycoon, MFL's own reports, Sleeper's history editor, leeger, league-page). Built.
- **Rule-based Hall of Fame with induction classes**: rare. Only League Tycoon markets an explicit Hall of Fame page; nobody found has automatic induction rules and a watch list. Built, and a differentiator.
- **Retrospective trade ledger with verdicts**: found in no commercial product. Three open-source projects compute something similar (FantasyFootballAnalyzer, LeaguePulse trade trees, fantasy-football-wrapped trade insights). Built, and a differentiator.
- **Rookie-draft hindsight**: present only as a side feature elsewhere (ffwrapped draft grades, Dynasty Daddy ADP). Built; the per-franchise draft ranking already covers the "career draft grade" idea from FantasyFootballAnalyzer.
- **Value over replacement**: independently reinvented by jsoslow2/fantasy-football-models and ffsimulator. The baseline choice is on solid footing.
- **Transaction feed to Discord**: the first thing most bot authors build (dtcarls, SleeperLink, fleaflicker-dynasty-bot). Built.
- **Weekly recap and season wrap**: common in bots; the season-wrap format overlaps with the crowded "Wrapped" category. Built.
- The closest paid equivalent to the whole package is League Legacy at $36 per year, which supports MFL but has no Hall of Fame rules, trade verdicts, or draft hindsight. The two MFL-specific Discord bots on GitHub are abandoned (last touched 2019 and 2021).

## Ranked candidate features

Evidence = number of independent sources (products, bots, open-source projects, editorial) that ship or request it. Fit = how well it suits a static site plus webhook at $0 with no manual work. Effort is a rough size for this codebase.

| # | Feature | What people want | Evidence | Fit and effort |
|---|---|---|---|---|
| 1 | **Weekly awards in the Tuesday recap** | Highest and lowest score, biggest blowout, closest game, best and worst lineup decision (bench points left, efficiency), luckiest and unluckiest win. GameDayBot and dtcarls ship ten weekly trophies; Sleeper added native weekly trophies; award listicles are evergreen. | 8: GameDayBot, dtcarls bot (307 stars), metrics-weekly-report (227 stars), FantasyFootballAnalyzer, fantasy-football-wrapped, Sleeper, Fantasy Football Unlimited, Viking Awards | Small. Every input (scores, `opt_pts`, margins) is already in the model. One new recap field plus a site "weekly awards" archive if wanted. |
| 2 | **Formula power rankings** | A computed weekly ranking (record, points, margin, recent form, dominance matrix) rather than commissioner opinion. The most-shipped feature across bots and open-source projects. | 10: league-page (279 stars), power_ranker, metrics-weekly-report, wrapped, LeaguePulse, FantasyFootballAnalyzer, GameDayBot, Fantasy League Bot, Dynasty Daddy, KeepTradeCut | Small to medium. No canonical formula; pick one and show the components. Recap line plus a site table with week-over-week movement. |
| 3 | **Luck: expected wins, all-play record, schedule luck** | "Record if you played everyone every week" and wins above expectation. Sold as a paid tier by GameDayBot ("Fortune Index", $49.99/yr) and as a "skill vs luck report card" by StatChasers. | 7: FantasyFootballAnalyzer, wrapped, metrics-weekly-report, LeaguePulse, leeger, GameDayBot, StatChasers | Small. Needs only weekly scores across the league, already loaded. Adds columns to franchise season rows, career "skill vs luck" on franchise pages, and records ("luckiest season ever"). |
| 4 | **Playoff odds by simulation** | Probability of making the playoffs and of each seed, not just a standings list. Built independently by four open-source projects and Dynasty Daddy (10,000 seasons). | 7: ffsimulator, metrics-weekly-report, wrapped, LeaguePulse, Dynasty Daddy, Fantasy League Bot, ffwrapped | Medium. Remaining schedule and score history are on hand; needs the league's seeding and tiebreak rules encoded. Would upgrade the recap's "Playoff picture" field. |
| 5 | **Thursday matchup preview with series history** | "These two have met 9 times, X leads 5-4, last meeting was a 3-point game." A second weekly touchpoint, forward-looking. | 5: GameDayBot previews, dtcarls, Fantasy League Bot, ffwrapped rivalry profiles, Building the Legacy newsletter | Small. Head-to-head data exists; needs a Thursday schedule and preview state. |
| 6 | **Per-franchise "Wrapped" season pages** | Spotify-style shareable season summary per manager: best week, worst beat, nemesis, best trade. Five or more products compete on exactly this. | 6: ffwrapped, League Wrapped, ffrec.app, Dynasty Daddy recap, League Rewind, kt474/fantasy-football-wrapped (60 stars) | Medium. A rendering and design job over existing stats. Image cards for Discord are harder on a static build; HTML pages are easy. |
| 7 | **All-time rivalry matrix page** | One grid of every pairing's all-time record, blowouts, and closest games. | 5: leeger, LeaguePulse, league-page, Fantasy Record Book, League Legacy | Small. Data exists on franchise pages; this is one new page. |
| 8 | **Live rookie draft feed to Discord** | "Pick 1.05: X selects Y. Z is on the clock." Draft-turn alerts are the one dynasty feature a purpose-built bot shipped; MFL users otherwise watch for MFL's emails. | 2: fleaflicker-dynasty-bot, MFL email-watcher pattern | Small to medium. `draftResults` is public and timestamped; the minute poller can diff it during the draft window. |
| 9 | **Roster age and aging on franchise pages** | Average starter age, oldest core, age by position. No surveyed bot does this; dynasty offseason advice is all about aging curves. | 3: LeaguePulse value trends, dynasty offseason editorial, absence noted across all bots | Small. `players&DETAILS=1` returns `birthdate` publicly. |
| 10 | **Draft pick inventory page** | Every future pick each franchise owns, with origin, plus pick assets shown in trade posts. | 3: fleaflicker-dynasty-bot `/picks`, KeepTradeCut, dynasty offseason theme | Medium. `futureDraftPicks` needs an MFL API key (302 without login). The trade ledger's pick-resolution logic is reusable. |
| 11 | **Sunday lineup check** | Post teams with empty slots, bye-week starters, or OUT/Questionable starters before kickoff. Near-universal in bots ("players to monitor"). | 4: GameDayBot, dtcarls, SleeperLink, fleaflicker-dynasty-bot | Small to medium. `injuries` is public; current-week starters come from `weeklyResults`. Live in-game close-score alerts would need `liveScoring`, which requires login. |
| 12 | **Constitution, rulings log, manager bios, punishment and dues ledger** | A canonical rules page to end "that's not the rule" disputes; a shame ledger for last-place punishments; who has paid. league-page's constitution and bio pages are its most-forked feature; League Legacy sells "Commissioner HQ"; chasing dues is the most-named commissioner pain. | 5: league-page (1.3k forks), League Legacy, Building the Legacy, Yahoo/FantasyPros punishment listicles, Cheddar Up | Small in code, but the content is authored by the commissioner in config or markdown. Not derivable from MFL. |
| 13 | **Discord slash commands** | On-demand lookups: `/h2h`, `/record`, `/player`, `/trade`, `/odds`. The two most-starred open-source bots are broadcast-only and users ask for commands; GameDayBot's paid layer exists mainly to add them; Fantasy League Bot has 27. | 6: dtcarls README, GameDayBot, Fantasy League Bot, harambot, SleeperLink, dead MFL bots | Large. Needs a Discord application, an interactions endpoint with signature verification, and hosting (a Lambda function URL fits the free tier). Already deferred by the Hall of Records design. |
| 14 | **AI-written recap prose, with a tone setting** | Narrative recaps, roast mode, trash talk. At least six paid products launched 2024 to 2026 and ESPN added native AI insights. No product publishes retention evidence; the one documented success automated an already-loved commissioner email. | 9 supply-side: League Rewind, GameDayBot Elite, CommishCast, SmackScript, Fantasy Sports Reports, Recapr, ESPN, LeagueLoom, raymer/fantasy-football-recapper | Medium. Breaks the $0 rule slightly (a few cents a week) and adds a secret. Risk: novelty fades. Best done as a layer over the template recap, if at all. |
| 15 | **External dynasty values in the trade ledger** | KeepTradeCut or DynastyProcess values at the time of the trade, beside the retrospective verdict. | 5: KeepTradeCut, FantasyCalc, Dynasty Daddy, fleaflicker-dynasty-bot, LeaguePulse | Medium. Adds an external data dependency (DynastyProcess publishes open data on GitHub). |
| 16 | **Trade tree visualization** | Follow a pick through chained trades to the player it became. | 1: LeaguePulse | Medium. Pick resolution already exists in the ledger. Strong fit, weak demand evidence. |
| 17 | **Strength of schedule, regular vs playoff splits, median record** | Small companion stats. | 2 to 3 each | Small. Playoff record already appears on franchise pages. |
| 18 | **Trade veto polls, trash-talk generator, punishment wheel** | Novelty utilities. | 2: Commish Hub, Fantasy League Bot "taunt" | Small, but demand is thin and MFL owns the actual veto. Skip unless the league asks. |

## Recommended shortlist

Ordered by demand per unit of effort, and by what stays within the existing constraints (no login, no cost, no manual work).

1. **Analytics layer** (rows 1, 2, 3, 7): weekly awards, power rankings, luck and all-play, rivalry matrix. Cheapest, most converged, and feeds both the site and the Tuesday recap.
2. **Thursday preview** (row 5): a second weekly touchpoint built from data already on the franchise pages.
3. **Playoff odds** (row 4): the one heavier analytics item, but four unrelated builders each made it.
4. **Dynasty pack without login** (rows 8, 9): live rookie draft feed and roster age. No surveyed bot does either; both are public data.
5. **Commissioner content pages** (row 12): only if the owner wants to write and maintain the content.

Defer pending league feedback or credentials: Wrapped pages (row 6, presentation-heavy), pick inventory (row 10, needs API key), lineup check (row 11, partly needs login), slash commands (row 13, new infrastructure), AI prose (row 14, cost and staleness risk), external values (row 15, dependency).

## Questions the league feedback should answer

- Do members read the Tuesday recap, and would a Thursday preview be welcome or noise?
- Do they want on-demand lookups in Discord, or is the site enough?
- Is there appetite for a written voice (roast, sportscaster) or is the numbers-only tone preferred?
- Which dynasty offseason content matters: rookie draft feed, pick inventory, roster aging?
- Should the site host the constitution and punishment history?

## Sources

Products: [League Legacy](https://leaguelegacy.io/), [League Tycoon](https://leaguetycoon.com/), [ffwrapped](https://ffwrapped.com/), [League Rewind](https://leaguerewind.com/), [Dynasty Daddy](https://dynasty-daddy.com/), [KeepTradeCut](https://keeptradecut.com/), [FantasyCalc](https://fantasycalc.com/), [Fantasy Record Book](https://fantasyrecordbook.com/features), [StatChasers report card](https://statchasers.com/fantasy-football-report-card/), [Commish Hub](https://commishhub.com/), [MFL league history](https://home.myfantasyleague.com/features/league-history/), [Sleeper history and trophies](https://sleeper.com/blog/league-history-and-weekly-trophies/).

Bots: [GameDayBot](https://www.gamedaybot.com/), [dtcarls/fantasy_football_chat_bot](https://github.com/dtcarls/fantasy_football_chat_bot) (issues [#77](https://github.com/dtcarls/fantasy_football_chat_bot/issues/77), [#91](https://github.com/dtcarls/fantasy_football_chat_bot/issues/91)), [Fantasy League Bot](https://fantasyleaguebot.com/), [SleeperLink](https://evildrporkchop.github.io/SleeperLink/), [harambot](https://github.com/DMcP89/harambot), [tdmack/fleaflicker-dynasty-bot](https://github.com/tdmack/fleaflicker-dynasty-bot), [red-scott/discord-mfl-bot](https://github.com/red-scott/discord-mfl-bot), [rossfrank/mfldiscord](https://github.com/rossfrank/mfldiscord).

Open source: [leeger](https://github.com/joeyagreco/leeger), [league-page](https://github.com/nmelhado/league-page), [LeaguePulse](https://github.com/ebrown-32/LeaguePulse), [FantasyFootballAnalyzer](https://github.com/Krool/FantasyFootballAnalyzer), [ffscrapr](https://github.com/ffverse/ffscrapr), [ffsimulator](https://github.com/ffverse/ffsimulator), [fantasy-football-metrics-weekly-report](https://github.com/uberfastman/fantasy-football-metrics-weekly-report), [kt474/fantasy-football-wrapped](https://github.com/kt474/fantasy-football-wrapped), [dynastyprocess/data](https://github.com/dynastyprocess/data), [power-ranker](https://pypi.org/project/power-ranker/), [raymer/fantasy-football-recapper](https://github.com/raymer/fantasy-football-recapper).

AI content and rituals: [CommishCast](https://commishcast.ai/), [SmackScript](https://smackscript.com/), [Fantasy Sports Reports](https://www.fantasysportsreports.com/), [Recapr](https://www.recapr.ai/), [LeagueLoom prompts](https://leagueloom.com/prompts), [ESPN and IBM AI insights](https://www.nasdaq.com/press-release/new-ibm-watsonx-ai-powered-insights-help-elevate-espn-fantasy-football-2025-fantasy), [award ideas](https://www.fantasyfootballunlimited.com/fantasyfootballspotlight/2024/8/23/creative-awards-to-elevate-your-fantasy-football-league), [punishment ideas](https://www.fantasypros.com/2026/08/16-punishments-for-finishing-last-2026-fantasy-football/), [constitution template](https://www.fantasyfootballunlimited.com/fantasy-football-constitution), [Building the Legacy](https://buildingthelegacy.substack.com/).
