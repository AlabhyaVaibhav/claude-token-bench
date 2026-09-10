# claude-token-bench

Measure Claude output tokens/minute (and tokens/second) across model + effort
configurations, with a colorized, ranked terminal table.

```
+--------------------+------------------+----------+----------+------------+-----------+--------------------------+
| config             | model            |   tokens |     secs |    tok/min |   tok/sec |                          |
+--------------------+------------------+----------+----------+------------+-----------+--------------------------+
| sonnet5-high       | claude-sonnet-5  |     1290 |     14.4 |       5380 |      89.7 | ######################## |
| haiku4.5           | claude-haiku-4-5 |      766 |      9.3 |       4927 |      82.1 | ######################   |
| opus5-xhigh        | claude-opus-5    |     1906 |     24.5 |       4665 |      77.7 | #####################    |
| sonnet5-low        | claude-sonnet-5  |     1295 |     17.1 |       4551 |      75.9 | ####################     |
| opus5-high         | claude-opus-5    |     1751 |     24.4 |       4308 |      71.8 | ###################      |
+--------------------+------------------+----------+----------+------------+-----------+--------------------------+
```

Rows are ranked by tok/min descending; the bar column is a relative visual
(green/yellow/red by fraction of the fastest config). Failed configs show a
`FAILED` row with the error instead of dropping silently.

## What it measures

For each config in `CONFIGS` (`token_bench.py`), it streams one completion for
a fixed prompt, times the full request (`client.messages.stream(...)` open to
`get_final_message()`), and computes:

```
tok/sec = response.usage.output_tokens / elapsed_seconds
tok/min = tok/sec * 60
```

This is end-to-end throughput (network + generation), not raw decode speed —
useful for comparing what you'd actually observe in an app, not a lab number.

Default grid: `opus5-high`, `opus5-xhigh`, `sonnet5-high`, `sonnet5-low`,
`haiku4.5` — same model family, different `output_config.effort` levels.
Edit `CONFIGS` to add/remove models or effort levels.

## Install

```bash
pip install anthropic azure-identity   # azure-identity only needed for --provider foundry
```

## Usage

### Microsoft Foundry (default)

Authenticates via `az login` (Azure CLI credential), no static API key needed.

```bash
az login
python3 token_bench.py --provider foundry --resource <your-foundry-resource>
```

### Direct Anthropic API

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 token_bench.py --provider direct
```

### Options

| Flag | Default | Meaning |
|---|---|---|
| `--provider` | `foundry` | `foundry` or `direct` |
| `--resource` | none | Foundry resource name (required for `--provider foundry`) |
| `--runs` | `1` | Repeats per config, averaged |
| `--prompt` | a ~500-word TCP explainer prompt | Override the benchmark prompt |
| `--no-color` | off | Disable ANSI colors (auto-disabled when not a TTY) |

## Notes

- **Fast mode is excluded.** It's a beta, first-party-API-only feature not
  available on Microsoft Foundry, so it's left out of the grid for both
  providers to keep the comparison apples-to-apples.
- **This costs real money on every run.** Five configs × your `--runs` count
  × ~500-word completions. Trim `CONFIGS` or lower `--runs` for a cheap smoke
  test.
- **n=1 is noisy.** Token counts and latency vary run to run (server load,
  natural variance in completion length). Use `--runs 3` or more before
  drawing conclusions from the ranking.
