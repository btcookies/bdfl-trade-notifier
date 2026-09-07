# Fixtures

`raw/2020/` is a real MFL export of the BDFL league's actual 2020 season, captured with:

```bash
python -m hof --data tests/hof/fixtures --config data/config.toml fetch --year 2020
```

`weeklyResults/` was then pruned to just the weeks the tests need — a regular-season week,
the last regular-season week, the three bracket weeks, and the non-bracket week 17:

```bash
find tests/hof/fixtures/raw/2020/weeklyResults -name 'W*.json' \
  ! -name 'W01.json' ! -name 'W13.json' ! -name 'W14.json' \
  ! -name 'W15.json' ! -name 'W16.json' ! -name 'W17.json' -delete
```

`meta.json`'s `weeks: [1, 17]` reflects the full season that was fetched, not the pruned set
on disk — the loader globs `weeklyResults/W*.json` rather than trusting that range, so this is
harmless, but don't be surprised the two disagree. `players.json` was captured before pruning,
so it's a superset that also covers the dropped weeks.

2020 is a completed season, so this data won't change; regenerate with the command above if it
is ever lost.
