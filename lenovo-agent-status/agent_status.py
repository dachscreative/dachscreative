#!/usr/bin/env python3
"""Lenovo agent status: is the Vergabe agent graph running, and is it on the GPU?

Run this ON the Lenovo PC (a cloud session cannot see it) — in a terminal,
over SSH/Tailscale, or from a `claude remote-control` session:

    python3 agent_status.py [--pattern REGEX] [--samples N]

Standard library only. It prints the machine, each NVIDIA GPU with a short
utilisation graph, every process holding GPU memory, the agent processes,
the LangGraph API and the Ollama models, then a RESULT with the fix for
anything that is wrong. Exit code 0 means the agent is running on the GPU.
"""

import argparse
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime

# Words from the agent's command line (override with --pattern or AGENT_PATTERN).
DEFAULT_PATTERN = r"langgraph|vergabe|nexus|hermes"
# `langgraph dev` listens on 2024, `langgraph up` on 8123; both answer GET /ok.
LANGGRAPH_URLS = ("http://127.0.0.1:2024", "http://127.0.0.1:8123")
GPU_QUERY = (
    "index,name,driver_version,temperature.gpu,power.draw,power.limit,"
    "memory.used,memory.total,pstate"
)
HOT_C = 85  # laptop GPUs start throttling around here
SPARKS = "▁▂▃▄▅▆▇█"
GIB = 1024**3
SELF = os.path.basename(__file__)
WIDTH = shutil.get_terminal_size((100, 24)).columns

# Always talk to localhost directly, even when an HTTP proxy is configured.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def run(*cmd, timeout=10):
    """Run a command and return (ok, output); a missing binary is simply not ok."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    ok = proc.returncode == 0
    return ok, (proc.stdout if ok else proc.stdout + proc.stderr).strip()


def http_get(url, timeout=2):
    try:
        with _opener.open(url, timeout=timeout) as resp:
            return resp.read().decode()
    except (OSError, ValueError, http.client.HTTPException):
        return None


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def num(field):
    """nvidia-smi prints '[N/A]' for fields a GPU does not support."""
    try:
        return float(field)
    except ValueError:
        return None


def duration(seconds):
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d{hours:02d}h"
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s"


def spark(values):
    return "".join(SPARKS[min(int(v * len(SPARKS) / 100), len(SPARKS) - 1)] for v in values)


def clip(text, used):
    room = max(WIDTH - used, 20)
    return text if len(text) <= room else text[: room - 1] + "…"


def process_table():
    """pid -> (seconds running, command line) for every process."""
    ok, out = run("ps", "-eo", "pid=,etimes=,args=")
    table = {}
    for line in out.splitlines() if ok else []:
        fields = line.split(None, 2)
        if len(fields) == 3:
            table[int(fields[0])] = (int(fields[1]), fields[2])
    return table


def show_machine():
    vendor = read("/sys/class/dmi/id/sys_vendor")
    # Lenovo keeps the model name (e.g. "Legion 5 15ACH6H") in product_version
    # and only the machine type (e.g. "82JU") in product_name.
    model = read("/sys/class/dmi/id/product_version") or read("/sys/class/dmi/id/product_name")
    meminfo = dict(line.split(":", 1) for line in read("/proc/meminfo").splitlines() if ":" in line)
    total = int(meminfo.get("MemTotal", "0 kB").split()[0]) * 1024
    free = int(meminfo.get("MemAvailable", "0 kB").split()[0]) * 1024
    uptime = float((read("/proc/uptime").split() or ["0"])[0])
    load = "/".join(f"{x:.1f}" for x in os.getloadavg())
    print(f"Machine  : {f'{vendor} {model}'.strip() or 'unknown model'}, up {duration(uptime)}")
    print(f"  load   : {load} on {os.cpu_count()} CPUs, RAM {(total - free) / GIB:.1f} / {total / GIB:.1f} GB used")
    if "lenovo" not in vendor.lower():
        print("  note   : this is not a Lenovo — is this the right PC?")


def sample_utilisation(samples):
    """GPU utilisation is bursty; sample it once a second instead of trusting one reading."""
    util = {}
    for n in range(samples):
        if n:
            time.sleep(1)
        ok, out = run("nvidia-smi", "--query-gpu=index,utilization.gpu", "--format=csv,noheader,nounits")
        for line in out.splitlines() if ok else []:
            row = [f.strip() for f in line.split(",")]
            if len(row) == 2 and num(row[1]) is not None:
                util.setdefault(row[0], []).append(num(row[1]))
    return util


def explain_missing_gpu(output, problems):
    if shutil.which("nvidia-smi"):
        problems.append(
            "nvidia-smi cannot reach the NVIDIA driver: " + (output.splitlines() or ["?"])[0] + "\n"
            "     Usually the driver was not rebuilt after a kernel update: reboot first;\n"
            "     if that does not help: sudo ubuntu-drivers install && sudo reboot.\n"
            "     Hybrid-graphics Lenovo: `prime-select query` must say nvidia or on-demand."
        )
        return
    ok, pci = run("lspci")
    if not ok or "NVIDIA" in pci:
        problems.append("nvidia-smi is missing — install the NVIDIA driver: sudo ubuntu-drivers install && sudo reboot")
    else:
        problems.append(
            "No NVIDIA GPU is visible to the OS. On a Lenovo with switchable graphics check\n"
            "     the BIOS graphics mode (Hybrid or Discrete, not integrated/UMA only)."
        )


def show_gpus(samples, problems):
    print()
    ok, out = run("nvidia-smi", f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits")
    fields = GPU_QUERY.split(",")
    # Skip anything that is not a data row, e.g. an "infoROM is corrupted" warning.
    rows = [[f.strip() for f in line.split(",")] for line in out.splitlines()] if ok else []
    gpus = [dict(zip(fields, row)) for row in rows if len(row) == len(fields)]
    if not gpus:
        print("GPU      : no usable NVIDIA GPU")
        explain_missing_gpu(out, problems)
        return []
    util = sample_utilisation(samples)
    for gpu in gpus:
        index = gpu["index"]
        used, total = num(gpu["memory.used"]) or 0, num(gpu["memory.total"]) or 0
        temp, draw, limit = num(gpu["temperature.gpu"]), num(gpu["power.draw"]), num(gpu["power.limit"])
        gpu["util"] = util.get(index, [])
        print(f"GPU {index:<5}: {gpu['name']} (driver {gpu['driver_version']})")
        print(f"  VRAM   : {used / 1024:.1f} / {total / 1024:.1f} GB ({100 * used / total if total else 0:.0f}%)")
        print(
            f"  temp   : {'n/a' if temp is None else f'{temp:.0f}°C'}, power "
            f"{'n/a' if draw is None or limit is None else f'{draw:.0f} / {limit:.0f} W'}, {gpu['pstate']}"
        )
        if gpu["util"]:
            values = gpu["util"]
            print(
                f"  util   : {spark(values)}  avg {sum(values) / len(values):.0f}%, "
                f"max {max(values):.0f}% ({len(values)} samples, 1 s apart)"
            )
        if temp is not None and temp >= HOT_C:
            problems.append(
                f"GPU {index} is at {temp:.0f}°C and will throttle: fan profile to performance,\n"
                "     clean the vents, give the laptop air underneath."
            )
    return gpus


def show_gpu_processes(procs):
    ok, out = run("nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits")
    users = {}
    for line in out.splitlines() if ok else []:
        row = [f.strip() for f in line.split(",")]
        if len(row) == 2 and row[0].isdigit():
            users[int(row[0])] = num(row[1]) or 0
    print("\nProcesses on the GPU")
    for pid, mib in sorted(users.items(), key=lambda item: -item[1]):
        if pid in procs:
            age, args = procs[pid]
            print(f"  pid {pid:<7} {mib / 1024:4.1f} GB  up {duration(age):<7} {clip(args, 38)}")
        else:
            print(f"  pid {pid:<7} {mib / 1024:4.1f} GB  (not visible here: other container or user)")
    if not users:
        print("  none")
    return users


def show_agent(procs, pattern, gpu_users):
    rx = re.compile(pattern, re.IGNORECASE)
    agent = {pid: p for pid, p in procs.items() if rx.search(p[1]) and SELF not in p[1]}
    print(f"\nAgent (/{pattern}/)")
    for pid, (age, args) in sorted(agent.items()):
        on_gpu = f"  {gpu_users[pid] / 1024:.1f} GB GPU" if pid in gpu_users else ""
        print(f"  pid {pid:<7} up {duration(age):<7}{on_gpu} {clip(args, 30 + len(on_gpu))}")
    if not agent:
        print("  no matching process")
    api = next((url for url in LANGGRAPH_URLS if '"ok"' in (http_get(url + "/ok") or "")), None)
    print(f"  LangGraph API: {'up at ' + api if api else 'not listening on :2024 or :8123'}")
    return agent, api


def ollama_url():
    raw = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
    parts = urllib.parse.urlsplit(raw if "://" in raw else "http://" + raw)
    host = parts.hostname or "127.0.0.1"
    if host in ("0.0.0.0", "::"):  # a bind-all address, not one to connect to
        host = "127.0.0.1"
    return f"{parts.scheme}://{host}:{parts.port or 11434}"


def show_ollama(problems, have_gpu):
    url = ollama_url()
    print(f"\nOllama ({url})")
    body, models = http_get(url + "/api/ps"), None
    if body:
        try:
            models = json.loads(body).get("models") or []
        except (ValueError, AttributeError):
            pass
    if models is None:
        print("  not answering")
        if shutil.which("ollama"):
            problems.append(
                f"Ollama is installed but not answering at {url}:\n"
                "     sudo systemctl restart ollama   (logs: journalctl -u ollama -e)"
            )
        return None
    for model in models:
        name, size, vram = model.get("name", "?"), model.get("size") or 0, model.get("size_vram") or 0
        share = 100 * vram / size if size else 0
        if share >= 99.5:
            where = "100% GPU"
        elif not vram:
            where = "CPU only"
        else:
            where = f"{share:.0f}% GPU / {100 - share:.0f}% CPU"
        print(f"  {name:<30} {size / GIB:5.1f} GB  {where}")
        if have_gpu and not vram:
            problems.append(
                f"Ollama runs {name} on the CPU although a GPU is present.\n"
                "     Check `journalctl -u ollama -b | grep -iE 'cuda|gpu'`, then sudo systemctl restart ollama."
            )
        elif have_gpu and share < 99.5:
            problems.append(
                f"{name} only fits {share:.0f}% into VRAM; the rest runs on the CPU (slow).\n"
                "     Use a smaller model or quantisation, or a lower num_ctx, so it fits completely."
            )
    if not models:
        print("  no model loaded (Ollama loads on the first request, unloads after 5 min idle)")
    return models


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pattern",
        default=os.environ.get("AGENT_PATTERN", DEFAULT_PATTERN),
        help="regex matched against process command lines to find the agent (default: %(default)s)",
    )
    parser.add_argument("--samples", type=int, default=5, help="GPU utilisation samples, 1 s apart (default: 5)")
    args = parser.parse_args()

    print(f"Lenovo agent status on {socket.gethostname()} — {datetime.now():%Y-%m-%d %H:%M:%S}\n" + "=" * 60)
    problems = []
    show_machine()
    procs = process_table()
    gpus = show_gpus(max(args.samples, 1), problems)
    gpu_users = show_gpu_processes(procs) if gpus else {}
    agent, api = show_agent(procs, args.pattern, gpu_users)
    models = show_ollama(problems, bool(gpus))

    if not agent and not api:
        problems.insert(
            0,
            f"Agent not running: no process matches /{args.pattern}/ and no LangGraph API answers.\n"
            "     Start it, or rerun with --pattern '<a word from its command line>'.",
        )
    on_gpu = bool(gpu_users) or any(m.get("size_vram") for m in models or [])
    # Ollama up with nothing loaded just means no request in the last 5 minutes.
    idle = models == []
    if gpus and not on_gpu and not idle:
        problems.append(
            "Nothing is computing on the GPU: no process holds GPU memory.\n"
            "     Is the model server (Ollama) running, and is the agent pointed at it?"
        )

    print()
    if problems:
        print(f"RESULT: {len(problems)} problem(s)")
        for n, text in enumerate(problems, 1):
            print(f"  {n}. {text}")
        return 1
    if not on_gpu:
        print(
            "RESULT: OK — the agent is running; the GPU is idle because Ollama has no model loaded\n"
            "        (it unloads after 5 min without requests, so no Vergabe work came in lately)."
        )
    elif any(max(gpu["util"], default=0) > 0 for gpu in gpus):
        print("RESULT: OK — the agent is running and its model is on the GPU.")
    else:
        print("RESULT: OK — the agent is running and its model is on the GPU, but the GPU was idle during the sample.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
