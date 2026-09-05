# BDFL Discord Notifier: Design

Date: 2026-09-04 (updated 2026-09-05 to match the implementation)
Status: implemented on branch `discord-port`; awaiting owner deploy
Repo: `btcookies/bdfl-trade-notifier`, branch `discord-port`

## 1. Goal

Replace the GroupMe trade notifier with a Discord notifier that:

- posts a completed trade or processed blind-bid waiver claim to the league's Discord channel within about one minute;
- needs no manual configuration when MFL rolls the league to a new year;
- runs at $0 inside the AWS always-free tier on the owner's pre-2025 account;
- stores every transaction with its league year so a later hall-of-fame phase can query history.

## 2. Decisions already made with the owner

| Topic | Decision |
|---|---|
| Discord integration | Channel webhook. No bot application until slash commands are needed. |
| Platform | Stay on AWS. Replace Serverless Framework v2 with AWS SAM. |
| Language and runtime | Python 3.13 on Lambda, arm64. |
| Cadence | Poll MFL every minute. |
| Scope | Port, modernize, zero-touch year detection, secrets in SSM, reliability fixes. Hall of fame is a separate future spec; only the `year` attribute lands now. |

Removed outright: GroupMe client, SQS queue and sender Lambda, players table and daily sync, franchises table and monthly sync, MFL username and password, the disabled close-games function, and the in-repo `pymfl` package (folded into one module).

## 3. Verified facts about the MFL API

All checked on 2026-09-04 against league 65522 without logging in.

- Base URL is `https://api.myfantasyleague.com/{year}/export?TYPE=...&L=65522&JSON=1`. Requests redirect to the league's host (currently `www45`); the client follows redirects.
- `TYPE=league` returns `league.history.league[]`, one entry per season with `year` and `url` (2016 through 2026 for this league), plus `league.franchises.franchise[]` with `id` and `name`, and `league.name` and `league.baseURL`.
- A year that does not exist yet returns HTTP 404 with an HTML body. An unknown league returns HTTP 200 with JSON `{"error": {"$t": "..."}}`.
- `TYPE=transactions&TRANS_TYPE=TRADE,BBID_WAIVER&DAYS=1` returns only those types, about 1 to 2 KB, in about 270 ms. When exactly one transaction matches, MFL may return a dict instead of a list.
  - Trade fields: `timestamp`, `franchise`, `franchise2`, `franchise1_gave_up`, `franchise2_gave_up`, `comments`, `expires`, `by_commish`, `type`.
  - Waiver fields: `timestamp`, `franchise`, `transaction`, `type` where `transaction` is `"{added_id},|{bid}|{dropped_id}"` and the dropped id may be empty.
- `TYPE=players&PLAYERS=a,b,c` returns only those players: `id`, `name` as `"Last, First"`, `position`, `team`, and sometimes `status`.
- Asset codes inside `*_gave_up` strings (comma separated, trailing comma):
  - a bare number is a player id;
  - `BB_20` is 20 blind-bid dollars;
  - `FP_0005_2027_3` is franchise 0005's 2027 round 3 pick, round one-based;
  - `DP_2_5` is the current year's round 3, pick 6. Per MFL docs, both numbers are one less than the real round and pick. The old code added one to the round only, so its pick numbers were wrong.
- Throttling: limits are unpublished and per IP. Exceeding them returns HTTP 429 with progressive throttling. MFL's guidance: wait one second between requests, cache, and never retry a failed request. A registered User-Agent gets about 2.5 times the limit. Registration is optional and left to the owner.

## 4. Architecture

One Lambda function, one DynamoDB table, one EventBridge Scheduler rule at `rate(1 minute)`, one Discord webhook, one SSM SecureString parameter.

Each invocation:

1. Load `LeagueInfo` (league year, league name, franchise id to name) from the warm-container cache. Refresh when missing or older than 6 hours using year detection (section 5). League info is fetched at most once per invocation: a record that references an unknown franchise triggers a refresh only when the cache was not already refreshed during this run, so on a cold start it renders as `Franchise 0099` and picks up the name on a later run.
2. Fetch transactions for the league year with `TRANS_TYPE=TRADE,BBID_WAIVER&DAYS=1`. Parse into records and compute each record's key.
3. Drop keys the warm cache already knows are `sent` or `skipped`. Batch-get the rest from the table.
4. For each record not in the table, resolve the player names it references (section 7) and put it with a conditional write. New records with a timestamp older than `NOTIFY_MAX_AGE_SECONDS` are stored as `skipped`; newer ones as `pending`.
5. Collect records in state `pending` with fewer than 5 attempts, whether new this poll or left over from a failed post, ordered by transaction time. Build embeds and post to Discord: one message per trade, one message for all waiver claims in this poll, with half a second between posts. Mark each `sent` on success. On a transient `DiscordError`, increment attempts and leave `pending`; on the fifth failure mark `failed` with a reason and raise so the alarm sees it. On a `DiscordPermanentError` mark `failed` with the reason immediately. Once a run has spent 12 seconds, remaining messages are deferred to the next poll and counted as `deferred`, which leaves room for one worst-case post inside the 30 second limit. Claims that share one Discord message succeed or fail together; when a waiver batch spans several messages, each message's claims are marked independently.
6. Emit one JSON log line: league year, counts fetched, new, skipped, sent, failed, deferred, store errors, backoff flag, and duration. The result is kept on the poller so the handler can log it even when the run raises.

MFL requests inside one invocation are spaced at least one second apart. A normal poll makes exactly one MFL request. A poll that finds new transactions makes two. A poll that refreshes league info makes one or two more.

Reliability rules:

- The table is the outbox. Correctness never depends on the warm cache: a key is remembered as final only after DynamoDB confirmed the terminal state, so a store failure after a successful post leaves the row `pending` and the next poll posts it once more (the accepted duplicate). DynamoDB errors during the notify step are logged and counted as `store_errors` rather than aborting the run.
- Reserved concurrency of 1 on the function prevents overlapping polls. If the account's concurrency limit rejects the setting, drop it; the conditional put still prevents duplicate rows, and only a double post during overlap becomes possible.
- The Scheduler rule has `MaximumRetryAttempts: 0`. A failed invocation is never retried by AWS. The next minute's poll is the retry.
- On MFL HTTP 429 the poller records an in-memory backoff of 5 minutes and raises. Polls during backoff return immediately without calling MFL and without error.
- On any other MFL failure the poller raises without retrying. The next poll starts fresh.

## 5. Year detection

```
def detect_league(now):
    for y in (now.year, now.year - 1):
        resp = GET /{y}/export?TYPE=league&L={league}&JSON=1
        if resp is 404 or "error" in resp.json(): continue   # year not open yet, or league not rolled over
        return LeagueInfo(year=y, name=league.name, franchises={id: name})
    raise LeagueNotFound
```

The newest season a poller should follow is the current calendar year when it exists on MFL and the prior year otherwise, so the league export's `history` list is intentionally not consulted for detection (it remains the backfill iterator for the hall of fame). A 429, a 5xx, or a network failure during detection propagates as an error rather than being mistaken for a missing year. Detection costs one request for most of the year and two in the weeks between January 1 and MFL opening the new season.

The detected league year is used for the transactions and players requests, for the `year` attribute on stored rows, and for rendering current-year draft picks. After a rollover the cache refreshes within 6 hours. Late transactions posted to the old year after a rollover are not polled; MFL locks prior years, so this is acceptable.

## 6. Data model

Table `${StackName}-transactions`, partition key `pk` (string), provisioned at 5 read and 5 write units, `DeletionPolicy` and `UpdateReplacePolicy` set to `Retain`, point-in-time recovery off.

| Attribute | Type | Meaning |
|---|---|---|
| `pk` | S | `TRADE#{timestamp}#{franchise}#{franchise2}` or `WAIVER#{timestamp}#{franchise}#{added_player_id}` |
| `type` | S | `TRADE` or `BBID_WAIVER` |
| `year` | N | league year the transaction belongs to |
| `timestamp` | N | MFL epoch seconds |
| `franchise_ids` | L | both franchises for a trade, one for a claim |
| `raw` | M | the MFL transaction exactly as received |
| `details` | M | rendered names and assets as of storage time (see below) |
| `summary` | S | one-line plain text, for logs and future search |
| `notify_state` | S | `pending`, `sent`, `skipped`, or `failed` |
| `notify_attempts` | N | failed post attempts so far |
| `first_seen_at` | N | epoch when the poller first stored it |
| `notified_at` | N | epoch when Discord accepted it; absent otherwise |
| `notify_error` | S | why a row is `failed`; empty otherwise |

`details` for a trade: `{"sides": [{"franchise_id", "franchise_name", "assets": [str]}], "comments": str}`. For a claim: `{"franchise_id", "franchise_name", "parsed": bool, "bid": str, "added": str, "dropped": str or null}`, with `"raw_transaction"` present when `parsed` is false. Storing rendered names preserves what the team and player were called at the time, which is what a hall of fame wants.

Writes use `attribute_not_exists(pk)`; that conditional put is the dedupe guarantee, and the batch read before it is only a cost optimization. Batch reads are strongly consistent and deduplicate their key list. `mark_sent` only transitions a row out of `pending`; attempt bumps and failure marks require the row to exist. Floats in an item are converted to `Decimal` before writing, and numeric attributes read back as `Decimal`. Keys include franchise ids so two trades processed in the same second do not collide. A global secondary index on `year` and `timestamp` is deferred to the hall-of-fame spec; adding one later is an online operation.

## 7. Rendering

Player lookups are on demand: the union of player ids referenced by this poll's new records goes into one `PLAYERS=` request. A player label is `First Last, TEAM POS`, converted from MFL's `Last, First`. Missing team or position is omitted. An id MFL does not return renders as `Unknown player (#id)` and never fails the poll.

Asset codes render as:

| Code | Rendered |
|---|---|
| player id | `George Kittle, SFO TE` |
| `BB_20` | `$20 blind bid dollars` |
| `FP_0005_2027_3` | `<franchise 0005 name> 2027 Round 3 pick`, or `Franchise 0005 2027 Round 3 pick` if the id is unknown |
| `DP_2_5` | `<league year> Round 3 Pick 6` |
| anything else | the raw code, with a warning logged |

Waiver bids render as `$3` when integral and `$3.50` otherwise. A `transaction` string that does not parse is stored with `summary` set to `unparsed waiver` and posted as a single line naming the franchise and the raw string, with a warning logged.

Franchise names come from `LeagueInfo`. An id not in the cache triggers one refresh; if still unknown it renders as `Franchise 0005`.

Text that enters an embed (franchise names, player labels, asset strings) is backslash-escaped for Discord markdown; the stored `details` and `summary` keep the plain text. Trade comments are intentionally left unescaped so members can use markdown in trade notes.

## 8. Discord messages

Every post is `POST {webhook}?wait=true` with body `{"embeds": [...], "allowed_mentions": {"parse": []}}`. No username is sent, so the name and avatar configured on the webhook in Discord apply and the bot's identity is managed there without a deploy. Disabling mention parsing means a team named `@everyone` cannot ping the server. The builder enforces Discord's limits: at most 10 embeds per message, 256 characters per title, 4096 per description, 25 fields, 256 per field name, 1024 per field value, and 6000 characters in total across every embed in one message (title, description, field names and values, footer). Embeds are grouped into messages by that character budget as well as by count.

Trade embed, one message per trade:

- title `🚨 Trade Completed`, color `0xE74C3C`;
- description: the trade comments when non-empty, truncated to 1000 characters;
- one field per side named `<Franchise> gives up` whose value is a bulleted list of rendered assets, or `• (nothing)`;
- footer `MFL · <league name> · <league year>` and the MFL timestamp as the embed timestamp.

Waiver embed, one message per poll:

- title `✅ Waiver Claims Processed`, color `0x2ECC71`;
- description: one line per claim, sorted by timestamp then franchise name: `**<Franchise>** won **<Player>** for $3` plus ` · dropped <Player>` when a player was dropped;
- when the description exceeds 4096 characters the lines split across embeds titled `✅ Waiver Claims Processed (2/3)`; embeds split across messages when a message would exceed 10 embeds or the 6000-character total;
- footer and timestamp as for trades, using the latest claim's timestamp.

Discord error handling: the client validates the message locally first (non-empty, at most 10 embeds, at most 6000 characters) and raises `DiscordPermanentError` when it can never be delivered. On HTTP 429 it reads `Retry-After` from the header or the JSON body; when the wait is 5 seconds or less it sleeps and retries once, otherwise it raises `DiscordError` immediately and the next poll retries. Any other 4xx raises `DiscordPermanentError`; 5xx and network errors raise `DiscordError`. Network error messages never include the webhook URL, since the URL contains the secret. Timeouts are 3 seconds to connect and 7 to read, so one post always fits inside the Lambda's 30 second budget. The MFL client uses the same split timeout. The poller marks a record `failed` immediately on `DiscordPermanentError` and counts every `DiscordError` as one attempt.

## 9. Configuration

Environment variables set by the template:

| Variable | Default | Purpose |
|---|---|---|
| `LEAGUE_ID` | `65522` | MFL league |
| `TABLE_NAME` | from the stack | transactions table |
| `WEBHOOK_PARAM_NAME` | `/bdfl/discord/webhook-url` | SSM SecureString holding the webhook URL |
| `NOTIFY_MAX_AGE_SECONDS` | `43200` | transactions older than this are stored silently |
| `MFL_USER_AGENT` | `bdfl-notifier/1.0 (+https://github.com/btcookies/bdfl-trade-notifier)` | sent on every MFL request; replace with a registered agent for higher limits |
| `LOG_LEVEL` | `INFO` | logging level |

The webhook URL is read from SSM with decryption on first use and cached for the container's life. For local runs, `DISCORD_WEBHOOK_URL` in the environment overrides SSM.

## 10. Infrastructure

`template.yaml` (SAM):

- Parameters: `LeagueId` (digits only), `WebhookParameterName` (must start with `/`), `AlertEmail` (default empty, must look like an address when set), `PollSchedule` (default `rate(1 minute)`, must be a `rate(...)` or `cron(...)` expression), `NotifyMaxAgeSeconds` (default 43200, at least 1), `MflUserAgent` (default as in section 9). Validation happens at deploy time so a typo fails the changeset rather than the first cold start.
- `TransactionsTable` as in section 6.
- `PollFunction`: `python3.13`, `arm64`, 256 MB, 30 second timeout, reserved concurrency 1, an inline policy allowing exactly `dynamodb:BatchGetItem`, `PutItem`, and `UpdateItem` on the table, and `ssm:GetParameter` on the webhook parameter's ARN (no `kms:Decrypt` is needed under the AWS-managed `aws/ssm` key). Event source `ScheduleV2` with `FlexibleTimeWindow` off and `MaximumRetryAttempts` 0. The function's `LoggingConfig` points at the explicit log group so the group is created before the function, and selects JSON log format; the handler passes the run summary as `extra` fields, which the runtime emits as top-level JSON keys the metric filters read.
- Explicit log group with 14 day retention, plus metric filters that turn the `store_errors` and `failed` counts in each run's summary line into `StoreErrors` and `FailedNotifications` metrics.
- Four CloudWatch alarms notifying an SNS topic with an email subscription, all present only when `AlertEmail` is set: `Errors` sum of 5 or more over 15 minutes (MFL backoff produces at most 3, so 5 means something else broke); `Invocations` below 1 over 15 minutes with missing data treated as breaching, so a disabled or broken schedule is noticed; `FailedNotifications` of 1 or more, since a dropped notification raises exactly once; `StoreErrors` sum of 5 or more over 15 minutes, since DynamoDB failures never raise out of the poll. `AlertEmail` defaults to empty (the guided prompt cannot accept an empty answer for a parameter without a default), so the README makes the choice explicit.
- Resources are tagged `Project: bdfl-notifier`.
- Outputs: table name, function name, and the alert topic ARN.

`samconfig.toml`: stack `bdfl-notifier`, region `us-east-1`, `CAPABILITY_IAM`, `resolve_s3`, no changeset confirmation. The only runtime dependency is `requests`, so `sam build` runs without a container.

## 11. Free-tier budget at one poll per minute

| Service | Monthly usage | Always-free allowance |
|---|---|---|
| Lambda invocations | 43,200 | 1,000,000 |
| CloudWatch alarms | 4 | 10 |
| Lambda compute at 256 MB, about 1 s each | about 11,000 GB-seconds | 400,000 GB-seconds |
| EventBridge Scheduler invocations | 43,200 | 14,000,000 |
| DynamoDB | 5 read and 5 write units provisioned | 25 and 25 |
| CloudWatch Logs ingestion | about 10 MB | 5 GB |
| MFL requests | about 1,500 per day | unpublished; guidance is one per second |

The owner's account predates the July 2025 free-tier change and keeps the legacy always-free allowances.

## 12. Error handling and edge cases

- MFL returns a dict for a single transaction: normalized to a list.
- MFL 404 or an error body for the current calendar year: year detection falls back to the prior year.
- MFL 429: 5 minute in-memory backoff, invocation raises, no retry inside the invocation.
- MFL 5xx or network failure: invocation raises, no retry; next minute is a fresh attempt.
- Discord accepted the post but the `sent` write failed: the next poll posts once more. Accepted.
- First deploy: transactions from the last 24 hours are fetched; those older than 12 hours are stored `skipped`; newer ones post. The dry-run script shows exactly what would post before deploying.
- Renamed franchise: names refresh within 6 hours.
- Trade with comments: shown as the embed description.
- Unknown asset code, unknown player, unparsable claim: rendered defensively and logged; the poll never fails on content.
- Year rollover in February or March: the new year is detected within 6 hours of MFL creating it.
- A pending record that ages out of the 1 day fetch window before a successful post is not retried further. That requires Discord to be down for a day, which the alarm would have surfaced.

## 13. Testing

Unit tests with pytest on Python 3.13:

- `assets`: every code type, zero-based current picks, unknown codes, name conversion, missing team or position.
- `messages`: golden embed dictionaries for a trade with and without comments, a waiver batch, description chunking at the 4096 limit, message chunking at 10 embeds.
- `mfl`: year detection when the current year exists, when it returns 404, when it returns an error body, and that a future year in history is ignored; 429 and 5xx propagating out of detection; dict-versus-list normalization; players lookup; network errors wrapped; one-second spacing using an injected clock and sleep, including after a failed request.
- `discord`: request body shape, 429 with `Retry-After` retried once, 5xx raising.
- `store` with moto `mock_aws`: conditional put returns false on duplicates, batch get, state transitions, attempt counter.
- `poller` with fake MFL, fake Discord, and moto: new trade is posted and marked sent; old transaction is skipped; a Discord failure leaves it pending and the next poll sends it; five failures mark it failed and raise; backoff skips MFL; cached keys skip the table.

`scripts/dry_run.py --days 7` fetches from MFL for real, renders every trade and claim as it would post, and prints the JSON. `--send` posts them and requires `DISCORD_WEBHOOK_URL` in the environment. The author runs the dry run against league 65522 before hand-off.

## 14. Continuous delivery

- `.github/workflows/ci.yml` on pull requests and pushes to `main` and `discord-port`: install dev requirements, run ruff and pytest, validate both templates with `sam validate --lint`, and run `sam build`. Read-only token, 15 minute timeout.
- `.github/workflows/deploy.yml` on push to `main`, only when the repository variable `AWS_DEPLOY_ROLE_ARN` is set: on an arm64 runner (matching the function's architecture) run ruff and pytest, `sam build` before any credentials exist, then assume the role via OIDC and `sam deploy --no-confirm-changeset --no-fail-on-empty-changeset`. A concurrency group prevents overlapping deploys. Every action and the SAM CLI are pinned to exact versions.
- `infra/github-oidc.yaml`: one-time CloudFormation template creating the GitHub OIDC provider (optional, for accounts that already have one) and a deploy role trusting `repo:btcookies/bdfl-trade-notifier:ref:refs/heads/main` with `aud` checked. Permissions cover CloudFormation, the SAM artifact bucket, and Lambda, DynamoDB, Scheduler, Logs, SNS, CloudWatch, and IAM role management scoped to resources named `bdfl-notifier*`. An explicit Deny stops the role from modifying its own policies, trust, or stack. The role can still create the function's roles, which deploying Lambda requires, so the branch must be protected.

## 15. Repository layout

```
template.yaml
samconfig.toml
pyproject.toml              # project metadata, pytest and ruff config
requirements-dev.txt        # pytest, moto, responses, ruff
src/
  handler.py                # Lambda entry point
  requirements.txt          # requests
  bdfl/
    __init__.py
    config.py               # Settings from env, webhook URL from SSM
    mfl.py                  # MflClient: league info, year detection, transactions, players
    models.py               # LeagueInfo, Player, Trade, WaiverClaim, parsing, keys
    assets.py               # asset code and player rendering
    messages.py             # embed builders and chunking
    discord.py              # DiscordWebhook
    store.py                # TransactionStore
    poller.py               # Poller.run and warm caches
tests/
scripts/dry_run.py
infra/github-oidc.yaml
.github/workflows/ci.yml
.github/workflows/deploy.yml
docs/superpowers/specs/
docs/superpowers/plans/
README.md
```

Deleted: `get_*.py`, `send_bdfl_messages.py`, `groupme/`, `pymfl/`, `test/`, `serverless.yml`, `package.json`, `package-lock.json`. `.gitignore` gains `.aws-sam/`, `__pycache__/`, `.venv/`, `.pytest_cache/`.

## 16. Migration and hand-off

Steps only the owner can do, in order:

1. `aws configure` with an IAM user or SSO profile for the account, region `us-east-1`.
2. In Discord: channel settings, Integrations, Webhooks, New Webhook, name it `BDFL`, copy the URL.
3. `aws ssm put-parameter --name /bdfl/discord/webhook-url --type SecureString --value '<url>'`.
4. `sam build && sam deploy --guided` the first time, accepting the defaults; `sam deploy` afterwards.
5. Watch the function's log group for the first few polls, or run the dry run with `--send` to preview.
6. Once satisfied, delete the old Serverless CloudFormation stack from the console. That removes the old functions, queue, and tables, and silences the GroupMe bot. Exporting the old `trades` table first is optional; the hall-of-fame backfill reads MFL directly.
7. Optional: register a User-Agent with MFL and set the `MflUserAgent` parameter. Optional: apply `infra/github-oidc.yaml` and set `AWS_DEPLOY_ROLE_ARN` for push-to-deploy.

## 17. Future work with hooks in place

- Hall of fame: add the `year` index, backfill every season listed in `history` into the same table with `notify_state` of `skipped`, snapshot standings and playoff results per season, and add a Discord application with an interactions endpoint on a Lambda Function URL for slash commands.
- Free-agent pickups and IR moves: add types to `TRANS_TYPE` and one renderer each.
- Close games on Sundays: a second scheduled function using `liveScoring`, reusing the Discord client.
