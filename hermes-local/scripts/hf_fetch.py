#!/usr/bin/env python3
"""Discover and download a Hermes GGUF quant from the Hugging Face Hub.

Listing is done against the public API so that a missing quant produces a
readable inventory of what the repo actually has, instead of a 404 on a
guessed filename. Download uses huggingface_hub, which resumes and verifies.

Usage: hf_fetch.py --repo REPO --quant Q4_K_M --dest DIR [--file NAME]
Prints the chosen filename (relative to DIR) on stdout as the last line.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://huggingface.co/api/models/{repo}"


def log(msg):
    print(msg, file=sys.stderr)


def list_repo_files(repo, token=None):
    req = urllib.request.Request(API.format(repo=repo))
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit(f"ERROR: {repo} needs authentication. Run `hf auth login` "
                     f"(or set HF_TOKEN) and accept the model licence on the Hub.")
        if e.code == 404:
            sys.exit(f"ERROR: repo '{repo}' not found on the Hub.\n"
                     f"Set HERMES_MODEL_REPO in config.env to a repo that "
                     f"publishes GGUF quants of Hermes 4 14B.")
        sys.exit(f"ERROR: Hub returned HTTP {e.code} for {repo}: {e.reason}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: cannot reach huggingface.co ({e.reason}). "
                 f"Check network, proxy and firewall.")
    return [s["rfilename"] for s in data.get("siblings", [])]


def pick(files, quant):
    ggufs = [f for f in files if f.lower().endswith(".gguf")]
    if not ggufs:
        sys.exit("ERROR: repo contains no .gguf files - it is probably the "
                 "unquantised model. Point HERMES_MODEL_REPO at a -GGUF repo.")

    matches = [f for f in ggufs if quant.lower() in f.lower()]
    if not matches:
        log("Available GGUF files in this repo:")
        for f in sorted(ggufs):
            log(f"    {f}")
        sys.exit(f"ERROR: no file matching quant '{quant}'. "
                 f"Set HERMES_QUANT to one of the above.")

    # Multi-part quants look like ...-00001-of-00003.gguf; llama.cpp is given
    # the first shard and loads the rest itself, but every shard must be local.
    shards = sorted(f for f in matches if "-of-" in f)
    if shards:
        return shards[0], shards
    # Prefer the shortest name to avoid picking an unrelated variant.
    best = sorted(matches, key=lambda f: (len(f), f))[0]
    return best, [best]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--quant", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--file", default="")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

    if args.file:
        primary, wanted = args.file, [args.file]
        log(f"Using explicitly configured file: {primary}")
    else:
        log(f"Listing {args.repo} ...")
        files = list_repo_files(args.repo, token)
        primary, wanted = pick(files, args.quant)
        log(f"Selected {primary}" + (f" ({len(wanted)} shards)" if len(wanted) > 1 else ""))

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        sys.exit("ERROR: huggingface_hub is not installed in this interpreter.")

    os.makedirs(args.dest, exist_ok=True)
    for name in wanted:
        log(f"Downloading {name} ...")
        hf_hub_download(
            repo_id=args.repo,
            filename=name,
            local_dir=args.dest,
            token=token,
        )
    print(os.path.basename(primary))


if __name__ == "__main__":
    main()
