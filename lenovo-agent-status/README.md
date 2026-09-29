# Lenovo agent status

One command that answers: **is the Vergabe agent graph on the Lenovo PC
running, and is it actually using the GPU?** When something is wrong, the
`RESULT` block says what to do about it.

It must run **on the Lenovo**, because it reads `nvidia-smi`, the process
list and the local Ollama / LangGraph ports. A cloud Claude session cannot
see the PC.

## Run it

```bash
cd ~/dachscreative && git pull          # wherever this repo lives on the Lenovo
python3 lenovo-agent-status/agent_status.py
```

From your phone or Mac, over SSH (e.g. Tailscale):

```bash
ssh <lenovo-host> 'python3 ~/dachscreative/lenovo-agent-status/agent_status.py'
```

Or run `claude remote-control` in a terminal on the Lenovo, open that
session in the Claude app, and ask it for the status.

Needs only Python 3.8+ on Linux (Ubuntu) with an NVIDIA GPU.

## What it checks

1. **Machine**: Lenovo model, uptime, load, RAM
2. **GPU**: model, driver, VRAM, temperature, power, and utilisation sampled
   once a second, because inference is bursty and one reading lies
3. **Processes on the GPU**: everything holding GPU memory, with its command line
4. **Agent**: processes matching `--pattern`, plus the LangGraph API on
   `:2024` (`langgraph dev`) or `:8123` (`langgraph up`)
5. **Ollama**: loaded models and how much of each sits in VRAM vs system RAM

Exit code `0` means the agent is running on the GPU (or idle with no model
loaded); `1` means a problem was found, so it also works from cron.

## Options

| Option | Default | Meaning |
|---|---|---|
| `--pattern` / `AGENT_PATTERN` | `langgraph\|vergabe\|nexus\|hermes` | Regex matched against command lines; use a word from your agent's start command |
| `--samples` | `5` | GPU utilisation samples, 1 s apart |
| `OLLAMA_HOST` | `127.0.0.1:11434` | Ollama server to query |

## Reading the RESULT

| RESULT says | Fix |
|---|---|
| Agent not running | Start it, or pass `--pattern` with a word from its command line |
| nvidia-smi cannot reach the NVIDIA driver | Reboot (driver not rebuilt after a kernel update); else `sudo ubuntu-drivers install && sudo reboot`. Hybrid graphics: `prime-select query` must not say `intel` |
| … only fits N% into VRAM | The model spills to the CPU: smaller model/quantisation or lower `num_ctx` |
| Ollama runs … on the CPU | `journalctl -u ollama -b \| grep -iE 'cuda\|gpu'`, fix the driver, `sudo systemctl restart ollama` |
| Nothing is computing on the GPU | Start Ollama and check which model endpoint the agent calls |
| GPU … will throttle | ≥ 85 °C: performance fan profile, clean the vents, raise the laptop |
| OK, GPU idle, no model loaded | Normal: Ollama unloads a model after 5 min without requests (`OLLAMA_KEEP_ALIVE=-1` keeps it loaded) |
