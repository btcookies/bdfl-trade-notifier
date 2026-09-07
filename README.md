# bdfl-trade-notifier

Posts completed trades and processed blind-bid waiver claims from the Barbara Dodson Fantasy League on MyFantasyLeague (MFL) to the league's Discord channel, within about a minute of MFL processing them.

## How it works

One Lambda function runs every minute. Each run:

1. detects the current league year from MFL's league export (no yearly config change needed),
2. fetches the last day of trades and blind-bid waivers in one request,
3. dedupes against a DynamoDB table that also acts as the outbox,
4. looks up only the players referenced by anything new,
5. posts embeds to a Discord webhook and marks each row as sent.

A row that fails to post is retried on the next run, up to five times. MFL rate limiting triggers a five-minute backoff. Everything fits in the AWS always-free tier at one poll per minute.

Design: `docs/superpowers/specs/2026-09-04-discord-notifier-design.md`.

## One-time setup

You need the AWS CLI and SAM CLI (`brew install awscli aws-sam-cli`) and Python 3.13.

1. Configure AWS credentials for the league's account:

   ```bash
   aws configure
   ```

   Use region `us-east-1`, or change `region` in `samconfig.toml`.

2. Create the Discord webhook: open the channel's settings, choose Integrations, then Webhooks, then New Webhook. The name and avatar you give it here are what every post shows (the code never overrides them), so name it what the league should see, for example `Barbara Dodson`. Copy the webhook URL.

3. Store the URL as an encrypted SSM parameter:

   ```bash
   aws ssm put-parameter --name /bdfl/discord/webhook-url --type SecureString --value 'https://discord.com/api/webhooks/...'
   ```

   The function reads this parameter lazily, on the first post rather than at deploy time. A missing or mistyped parameter name therefore stays invisible until the first trade arrives, and only then shows up as an error. Confirm the parameter exists before you rely on it, without printing the value:

   ```bash
   aws ssm get-parameter --name /bdfl/discord/webhook-url --query Parameter.Name
   ```

   A value that is present but malformed is worse: it fails with `ConfigError` on every poll until it is fixed, which trips the errors alarm.

4. Build and deploy. The first deploy is guided. Accept the defaults except `AlertEmail`: enter an address there. Leave it blank only if you accept having no alarms at all, because without it the stack creates no alarms and every failure is silent.

   ```bash
   sam build && sam deploy --guided
   ```

   Later deploys are just `sam build && sam deploy`. The guided run writes your answers, including the email, into the tracked `samconfig.toml` as `parameter_overrides`; decide whether you want that committed. If the deploy fails because the account cannot reserve concurrency, remove `ReservedConcurrentExecutions` from `template.yaml` and redeploy: dedupe still holds, and only a double post during an overlapping run becomes possible.

   With `AlertEmail` set the stack creates four alarms:

   - **errors**: five or more failed runs in 15 minutes. MFL throttling produces at most three in that window by design, so five means something else broke.
   - **stopped**: fewer than one invocation in 15 minutes, so a disabled schedule gets noticed instead of going quiet.
   - **dropped notification**: a trade or claim was given up on, either rejected outright by Discord or exhausted after five attempts. That raises only once, so it has its own alarm.
   - **store errors**: DynamoDB update failures inside the poll. Those never raise on their own, so without this alarm they would not be visible.

   The SNS email subscription has to be confirmed by clicking the link in the confirmation email. Until then the alarms deliver nothing. Check it:

   ```bash
   aws sns list-subscriptions-by-topic --topic-arn <AlertTopicArn output>
   ```

5. Confirm it is polling:

   ```bash
   sam logs --stack-name bdfl-notifier --name PollFunction --tail
   ```

   The function uses Lambda's JSON log format, so each run logs one record with the summary as top-level fields: `{"level": "INFO", "message": "poll", "event": "poll", "league_year": 2026, "fetched": 12, "new": 0, ...}`. A run that failed before detecting the league year omits `league_year`.

6. Once Discord posts look right, delete the old Serverless Framework stack from the CloudFormation console. It is probably named `bdfl-trade-notifier-dev`; confirm the name first:

   ```bash
   aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query "StackSummaries[?contains(StackName, 'bdfl-trade-notifier')].StackName"
   ```

   Deleting it removes the old functions, queue, and tables and silences the GroupMe bot. Do this within days, not weeks: the old stack's tables use all 25 read and 25 write units of the always-free tier (22 of each on its players table), so while both stacks exist the account sits at 30 units and bills roughly $3 a month.

## Preview what would post

```bash
python3.13 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
python scripts/dry_run.py --days 7
```

Prints the exact Discord payloads for the last 7 days without sending anything.

Add `--send` with `DISCORD_WEBHOOK_URL` set in the environment to post them for real, for example to test a new webhook. `--send` validates the URL first, waits half a second between messages, prints `sent i/n` as it goes, and exits non-zero naming the message it failed on. It does not touch DynamoDB, so re-running it posts everything again. It is for previewing a channel, not for backfilling the table.

## Development

```bash
source .venv/bin/activate
pytest                 # unit tests; no network, no AWS
ruff check src tests scripts hof
sam validate --lint
```

Layout: `src/handler.py` is the Lambda entry point; `src/bdfl/` holds the MFL client, rendering, Discord client, store, and poller; `tests/` mirrors it.

## Hall of Records (in progress)

`hof/` fetches every BDFL season from MFL into `data/raw/<year>/` and will build the records site. Design: `docs/superpowers/specs/2026-09-06-hall-of-records-design.md`.

```bash
python -m hof fetch            # refresh the current season; completed seasons are skipped
python -m hof fetch --year 2024   # refetch one season (delete data/raw/2024 first if it is marked complete)
python -m hof stats            # compute every stat and print the Hall of Fame calibration report
```

## Operations

- **Schedule:** the `PollSchedule` parameter, default `rate(1 minute)`.
- **First-deploy replay:** transactions older than `NotifyMaxAgeSeconds` (default 12 hours) are stored without posting.
- **Higher MFL limits:** register a client User-Agent on MFL's API page and set the `MflUserAgent` parameter.
- **Logs:** 14 day retention in the function's log group.
- **Private league:** MFL supports an `APIKEY` query parameter for exports. If the league is ever made private, add it to `MflClient._get` and store the key in SSM alongside the webhook URL.

### Reading a run

Each run logs one JSON line with `league_year`, `fetched`, `new`, `skipped`, `sent`, `failed`, `deferred`, `store_errors`, `backoff`, and `duration_ms`.

- `deferred` means the run hit its 12 second budget and left rows pending for the next minute. A large backlog drains across successive runs.
- `store_errors` counts DynamoDB update failures. When one lands after a successful post, the row stays pending and gets posted once more the next minute. That duplicate is the accepted trade-off; the alternative is dropping the message.
- A row that fails permanently carries a `notify_error` reason in the table, which says whether Discord rejected it outright or it exhausted its five attempts.

### Rotating the webhook

The webhook URL is cached for the life of the Lambda container. After changing the SSM value, either wait for the container to recycle or force one:

```bash
aws lambda update-function-configuration --function-name bdfl-notifier-poll --description "rotated $(date +%F)"
```

Setting `LOG_LEVEL` to `DEBUG` affects only this project's loggers. The AWS SDK and HTTP transport loggers are pinned to `WARNING` so the webhook URL never reaches the logs.

### Rebuilding the stack

The table has `DeletionPolicy: Retain`, so deleting the stack leaves `bdfl-notifier-transactions` behind, and re-creating the stack under the same name then fails on the existing table. Either delete the table first:

```bash
aws dynamodb delete-table --table-name bdfl-notifier-transactions
```

and accept that transactions from the last 12 hours will be posted again, or import it into the new stack.

If a failed deploy leaves the log group behind, delete it and redeploy:

```bash
aws logs delete-log-group --log-group-name /aws/lambda/bdfl-notifier-poll
```

## Push-to-deploy (optional)

1. Check whether the account already has a GitHub OIDC provider:

   ```bash
   aws iam list-open-id-connect-providers
   ```

   An account can hold only one provider for `token.actions.githubusercontent.com`. If it is already listed, add `--parameter-overrides CreateOidcProvider=false` to the next step and the existing one is reused.

2. Apply the one-time role:

   ```bash
   aws cloudformation deploy --template-file infra/github-oidc.yaml --stack-name bdfl-notifier-github-oidc --capabilities CAPABILITY_NAMED_IAM
   ```

3. Copy the `DeployRoleArn` output into a repository **variable** named `AWS_DEPLOY_ROLE_ARN`, under Settings, Secrets and variables, Actions, on the Variables tab. It must be a variable and not a secret: the workflow's `if:` gate reads variables only, and with a secret the deploy job silently shows as skipped. The account id in the ARN is not sensitive.

4. Pushes to `main` then run lint, tests, `sam build`, and `sam deploy` on an arm64 runner. Pull requests run lint, tests, template validation, and a build only. To turn push-to-deploy off, delete the variable.

The deploy passes no parameter overrides, so `AlertEmail` and the other parameters keep the values from the last local `sam deploy --guided`. Change them locally, not in the workflow. Push the branch before merging it so the CI workflow runs at least once on a real runner.

The deploy role can create the function's IAM roles, which is inherent to deploying Lambda. It is explicitly denied from modifying itself or its own stack, and the workflow's actions are pinned to commit SHAs. Protect `main` by requiring a pull request and the CI check, so a deploy always follows a green run.

## Future

The transactions table stores the league year and rendered details for every trade and claim, which is the seed for a hall-of-fame feature. MFL's league export lists every season since 2016, so prior years can be backfilled. Slash commands would add a Discord application and an interactions endpoint alongside this poller. `scripts/dry_run.py` and `bdfl.poller.build_batches` are the seams either one would reuse: the script already fetches and renders a date range without touching AWS, and `build_batches` turns records into the exact messages to post.
