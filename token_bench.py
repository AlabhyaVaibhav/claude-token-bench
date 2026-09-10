#!/usr/bin/env python3
"""Measure output tokens/minute across Claude API configs (model x effort).

Two providers:
  --provider foundry (default): Microsoft Foundry via Azure CLI auth (az login).
      Fast mode is not available on Foundry (first-party API only), so it's
      excluded from the grid regardless of provider.
  --provider direct: first-party Claude API via ANTHROPIC_API_KEY.

Usage:
  python3 token_bench.py --provider foundry --resource my-resource
  python3 token_bench.py --provider direct
"""
import argparse
import sys
import time

import anthropic

PROMPT_DEFAULT = (
    "Write a detailed 500-word explanation of how TCP congestion control works, "
    "covering slow start, congestion avoidance, and fast retransmit."
)

CONFIGS = [
    {"name": "opus5-high", "model": "claude-opus-5", "effort": "high"},
    {"name": "opus5-xhigh", "model": "claude-opus-5", "effort": "xhigh"},
    {"name": "sonnet5-high", "model": "claude-sonnet-5", "effort": "high"},
    {"name": "sonnet5-low", "model": "claude-sonnet-5", "effort": "low"},
    {"name": "haiku4.5", "model": "claude-haiku-4-5", "effort": None},
]


def build_client(provider: str, resource: str | None):
    if provider == "direct":
        return anthropic.Anthropic()

    from azure.identity import AzureCliCredential, get_bearer_token_provider

    if not resource:
        raise SystemExit("--resource is required for --provider foundry")
    token_provider = get_bearer_token_provider(
        AzureCliCredential(), "https://cognitiveservices.azure.com/.default"
    )
    return anthropic.AnthropicFoundry(resource=resource, azure_ad_token_provider=token_provider)


def run_once(client, cfg: dict, prompt: str) -> dict:
    kwargs = dict(
        model=cfg["model"],
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    if cfg["effort"] is not None:
        kwargs["output_config"] = {"effort": cfg["effort"]}

    start = time.perf_counter()
    with client.messages.stream(**kwargs) as stream:
        message = stream.get_final_message()
    elapsed_s = time.perf_counter() - start

    output_tokens = message.usage.output_tokens
    tpm = output_tokens / (elapsed_s / 60)
    return {"elapsed_s": elapsed_s, "output_tokens": output_tokens, "tpm": tpm}


DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"
BAR_WIDTH = 24


def _color(use_color: bool, code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if use_color else text


def render_table(rows: list[dict], use_color: bool) -> str:
    """rows: dicts with name, model, tokens, secs, tpm (tpm=None means failed)."""
    ok_rows = [r for r in rows if r["tpm"] is not None]
    max_tpm = max((r["tpm"] for r in ok_rows), default=1)

    headers = ["config", "model", "tokens", "secs", "tok/min", ""]
    widths = [18, 16, 8, 8, 10, BAR_WIDTH]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    lines = [sep]
    header_cells = [h.ljust(w) if h == "config" or h == "model" else h.rjust(w) for h, w in zip(headers, widths)]
    lines.append("| " + " | ".join(_color(use_color, BOLD, c) for c in header_cells) + " |")
    lines.append(sep)

    for r in sorted(rows, key=lambda r: (r["tpm"] is None, -(r["tpm"] or 0))):
        if r["tpm"] is None:
            cells = [
                r["name"].ljust(widths[0]),
                r["model"].ljust(widths[1]),
                "-".rjust(widths[2]),
                "-".rjust(widths[3]),
                _color(use_color, RED, "FAILED".rjust(widths[4])),
                _color(use_color, DIM, str(r["error"])[:BAR_WIDTH].ljust(widths[5])),
            ]
        else:
            frac = r["tpm"] / max_tpm if max_tpm else 0
            bar_len = max(1, round(frac * BAR_WIDTH))
            bar = "#" * bar_len
            bar_color = GREEN if frac > 0.85 else (YELLOW if frac > 0.5 else RED)
            cells = [
                _color(use_color, CYAN, r["name"].ljust(widths[0])),
                r["model"].ljust(widths[1]),
                f"{r['tokens']:.0f}".rjust(widths[2]),
                f"{r['secs']:.1f}".rjust(widths[3]),
                _color(use_color, BOLD, f"{r['tpm']:.0f}".rjust(widths[4])),
                _color(use_color, bar_color, bar.ljust(widths[5])),
            ]
        lines.append("| " + " | ".join(cells) + " |")

    lines.append(sep)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default=PROMPT_DEFAULT)
    parser.add_argument("--runs", type=int, default=1, help="repeats per config, averaged")
    parser.add_argument("--provider", choices=["foundry", "direct"], default="foundry")
    parser.add_argument("--resource", default=None, help="Foundry resource name (foundry provider only)")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors in output")
    args = parser.parse_args()

    use_color = not args.no_color and sys.stdout.isatty()
    client = build_client(args.provider, args.resource)

    rows = []
    for cfg in CONFIGS:
        print(_color(use_color, DIM, f"running {cfg['name']}..."), file=sys.stderr)
        results = []
        error = None
        for _ in range(args.runs):
            try:
                results.append(run_once(client, cfg, args.prompt))
            except anthropic.APIStatusError as e:
                error = f"{e.status_code} {e.message}"
                results = []
                break
        if not results:
            rows.append({"name": cfg["name"], "model": cfg["model"], "tpm": None, "error": error})
            continue
        rows.append(
            {
                "name": cfg["name"],
                "model": cfg["model"],
                "tokens": sum(r["output_tokens"] for r in results) / len(results),
                "secs": sum(r["elapsed_s"] for r in results) / len(results),
                "tpm": sum(r["tpm"] for r in results) / len(results),
            }
        )

    print()
    print(render_table(rows, use_color))


if __name__ == "__main__":
    main()
