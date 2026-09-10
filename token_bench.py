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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default=PROMPT_DEFAULT)
    parser.add_argument("--runs", type=int, default=1, help="repeats per config, averaged")
    parser.add_argument("--provider", choices=["foundry", "direct"], default="foundry")
    parser.add_argument("--resource", default=None, help="Foundry resource name (foundry provider only)")
    args = parser.parse_args()

    client = build_client(args.provider, args.resource)

    print(f"{'config':<18} {'model':<16} {'tokens':>8} {'secs':>8} {'tok/min':>10}")
    for cfg in CONFIGS:
        results = []
        for _ in range(args.runs):
            try:
                results.append(run_once(client, cfg, args.prompt))
            except anthropic.APIStatusError as e:
                print(f"{cfg['name']:<18} FAILED: {e.status_code} {e.message}")
                results = []
                break
        if not results:
            continue
        avg_tokens = sum(r["output_tokens"] for r in results) / len(results)
        avg_secs = sum(r["elapsed_s"] for r in results) / len(results)
        avg_tpm = sum(r["tpm"] for r in results) / len(results)
        print(
            f"{cfg['name']:<18} {cfg['model']:<16} {avg_tokens:>8.0f} "
            f"{avg_secs:>8.1f} {avg_tpm:>10.0f}"
        )


if __name__ == "__main__":
    main()
