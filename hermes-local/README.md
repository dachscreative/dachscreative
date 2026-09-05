# Hermes 4 14B — local deployment

Serves [Hermes 4 14B](https://huggingface.co/NousResearch) from Nous Research on
your own Ubuntu machine, behind an OpenAI-compatible HTTP API, as a systemd
service that survives reboots.

The stack is [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`
running a 4-bit GGUF quant. That choice keeps one setup working on both CPU-only
boxes and NVIDIA GPUs — the same scripts detect CUDA and offload layers when a
GPU is present.

## Quick start

```bash
git clone <this repo> && cd hermes-local
./scripts/00-preflight.sh     # read-only: can this machine run it?
./install.sh                  # everything, in order
```

`install.sh` needs `sudo` for the dependency, service-user and systemd steps; it
escalates on its own where required, so run it as your normal user.

When it finishes, Hermes answers at `http://127.0.0.1:8080/v1`:

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"hermes-4-14b","messages":[{"role":"user","content":"hi"}]}'
```

There is also a browser UI at <http://127.0.0.1:8080>.

## What each step does

| Step | Script | Needs root | What it does |
|---|---|---|---|
| 0 | `00-preflight.sh` | no | Checks CPU, RAM, VRAM, disk and Hub reachability against what the configured quant needs. Changes nothing. |
| 1 | `01-install-deps.sh` | yes | `apt` build toolchain, creates the `hermes` service user and `/opt/hermes`. |
| 2 | `02-build-llama.sh` | no | Clones and builds `llama-server`. Enables CUDA automatically if `nvcc` is present. |
| 3 | `03-fetch-model.sh` | no | Discovers and downloads the GGUF quant from the Hub. Resumable. |
| 4 | `04-install-service.sh` | yes | Renders and starts `hermes.service`, then waits for `/health`. |
| 5 | `05-smoke-test.sh` | no | Health, model listing, a chat completion, and a reasoning-mode request. |

To try the server before committing to a systemd service, skip step 4 and run
`./scripts/run-foreground.sh` — same flags, in your terminal, Ctrl-C to stop.

## Configuration

Everything is in `config.env`, and every value can be overridden per-invocation:

```bash
HERMES_PORT=9000 HERMES_CTX=32768 ./scripts/04-install-service.sh
```

The settings you are most likely to touch:

- **`HERMES_QUANT`** (default `Q4_K_M`, ~9 GB) — drop to `Q4_K_S` if you are
  short on RAM, raise to `Q5_K_M`/`Q6_K` for a little more quality if you have
  room.
- **`HERMES_CTX`** (default `16384`) — context window. The KV cache grows with
  this; halve it if you hit memory pressure.
- **`HERMES_NGL`** (default `auto`) — GPU layers. `auto` means all layers on a
  CUDA box, none otherwise. If the GPU OOMs, set a partial count like `24` to
  split between GPU and CPU.
- **`HERMES_HOST`** (default `127.0.0.1`) — loopback only. See *Exposing it*.
- **`HERMES_API_KEY`** (default empty) — when set, clients must send it as a
  Bearer token, and it is stored in `/etc/hermes.env` (mode 0640) rather than in
  the world-readable unit file.

### Model repo

`HERMES_MODEL_REPO` defaults to `NousResearch/Hermes-4-14B-GGUF`. **Verify this
before your first run** — I could not reach `huggingface.co` from the
environment where these scripts were written, so the default is not confirmed
against the live Hub. If the repo name is wrong or has no GGUF files, step 3
fails with a clear message rather than a mystery 404, and if the quant is
missing it prints every GGUF file the repo does have so you can pick one:

```bash
HERMES_QUANT=Q5_K_M ./scripts/03-fetch-model.sh
```

Community GGUF conversions (e.g. from `bartowski` or `mradermacher`) work
equally well — point `HERMES_MODEL_REPO` at one. If the repo is gated, run
`hf auth login` or export `HF_TOKEN` first.

## Performance expectations

Hermes 4 14B at Q4_K_M needs ~9 GB for weights plus 1–2 GB of KV cache at 16k
context.

| Hardware | Expectation |
|---|---|
| 16 GB+ VRAM (RTX 4080/4090, A5000) | Fully on GPU, ~30–60 tok/s |
| 8–12 GB VRAM | Partial offload; set `HERMES_NGL` to ~20–30, expect ~10–20 tok/s |
| CPU only, 16 GB RAM | Works, ~3–6 tok/s on 4–8 cores. Usable for batch work, sluggish for chat |
| Under 12 GB RAM, no GPU | Use `Q4_K_S` and a smaller `HERMES_CTX`, or expect swapping |

`00-preflight.sh` prints the estimate for your actual machine.

## Reasoning mode

Hermes 4 is a hybrid reasoning model: it answers directly by default, and
produces an explicit chain of thought when the system prompt asks it to. The
server runs with `--jinja` so the model's own chat template is used and
`<think>` blocks are parsed into the `reasoning_content` field.

```json
{
  "model": "hermes-4-14b",
  "messages": [
    {"role": "system", "content": "You are a deep thinking AI. Reason step by step inside <think></think> tags before answering."},
    {"role": "user", "content": "..."}
  ]
}
```

Step 5 exercises this path, so you can see which form your build returns.

## Operating it

```bash
systemctl status hermes          # is it up?
journalctl -u hermes -f          # live logs
systemctl restart hermes         # after changing config
./scripts/05-smoke-test.sh       # re-verify end to end
```

After editing `config.env`, re-run `./scripts/04-install-service.sh` to
re-render the unit — editing `config.env` alone does not change the running
service.

## Exposing it

The default binds to `127.0.0.1`, so nothing off the machine can reach it. This
is deliberate: `llama-server` has no authentication unless you set
`HERMES_API_KEY`, and anyone who can reach the port can use your GPU and read
every prompt.

If you need it on your LAN, set an API key *and* the bind address together:

```bash
HERMES_HOST=0.0.0.0 HERMES_API_KEY="$(openssl rand -hex 32)" ./scripts/04-install-service.sh
```

Do not put it on the public internet without a reverse proxy handling TLS and
rate limiting.

## Uninstalling

```bash
sudo ./scripts/uninstall.sh            # remove service and binaries, keep weights
sudo ./scripts/uninstall.sh --purge    # remove everything including the model
```

## Licensing

Hermes 4 is a fine-tune, so the weights carry the base model's upstream licence
in addition to Nous Research's terms. Check the model card on the Hub before
commercial use — these scripts do not and cannot grant you rights to the
weights.
