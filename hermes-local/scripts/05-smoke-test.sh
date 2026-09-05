#!/usr/bin/env bash
# Verify the running server: health, model listing, a chat completion, and
# Hermes' reasoning mode. Exits non-zero on the first real failure.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
need_cmd curl; need_cmd python3

base="http://${HERMES_HOST}:${HERMES_PORT}"
auth=()
[ -n "$HERMES_API_KEY" ] && auth=(-H "Authorization: Bearer $HERMES_API_KEY")

info "target: $base"

# 1. health
info "1/4 health"
curl -sf -m 10 "${auth[@]}" "$base/health" >/dev/null \
  || die "server not answering at $base - is it running? (systemctl status hermes)"
ok "healthy"

# 2. model listing (OpenAI-compatible)
info "2/4 model listing"
models=$(curl -sf -m 10 "${auth[@]}" "$base/v1/models") || die "/v1/models failed"
echo "$models" | python3 -c '
import json,sys
d=json.load(sys.stdin)
ids=[m["id"] for m in d.get("data",[])]
print("    served models:", ", ".join(ids) or "(none)")
sys.exit(0 if ids else 1)
' || die "server reports no loaded model"
ok "model loaded"

# 3. chat completion, with timing
info "3/4 chat completion (this is the real latency test)"
start=$(date +%s)
resp=$(curl -sf -m 300 "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{
    "model": "hermes-4-14b",
    "messages": [{"role":"user","content":"Reply with exactly the word: pong"}],
    "max_tokens": 16,
    "temperature": 0
  }' "$base/v1/chat/completions") || die "chat completion request failed"
elapsed=$(( $(date +%s) - start ))

echo "$resp" | python3 -c '
import json,sys
d=json.load(sys.stdin)
msg=d["choices"][0]["message"]["content"]
u=d.get("usage",{})
print("    reply:", repr(msg.strip()[:120]))
print("    tokens:", u.get("completion_tokens","?"), "completion /", u.get("prompt_tokens","?"), "prompt")
' || die "could not parse chat response: $resp"
ok "chat completion succeeded in ${elapsed}s"

# 4. reasoning mode - Hermes 4 emits <think> blocks when asked to reason
info "4/4 reasoning mode"
r=$(curl -sf -m 300 "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{
    "model": "hermes-4-14b",
    "messages": [
      {"role":"system","content":"You are a deep thinking AI. Reason step by step inside <think></think> tags before answering."},
      {"role":"user","content":"If 3 machines make 3 widgets in 3 minutes, how long do 100 machines take to make 100 widgets?"}
    ],
    "max_tokens": 512,
    "temperature": 0.6
  }' "$base/v1/chat/completions") || die "reasoning request failed"

echo "$r" | python3 -c '
import json,sys
d=json.load(sys.stdin)
m=d["choices"][0]["message"]
content=m.get("content") or ""
reasoning=m.get("reasoning_content") or ""
if reasoning:
    print("    reasoning_content returned:", len(reasoning), "chars (parsed by --jinja)")
elif "<think>" in content:
    print("    inline <think> block returned:", len(content), "chars")
else:
    print("    note: no explicit reasoning block; model answered directly")
print("    answer tail:", repr(content.strip()[-160:]))
'
ok "reasoning mode responded"

echo
ok "all checks passed - Hermes is serving at $base"
echo "    OpenAI-compatible base URL : $base/v1"
echo "    web UI                     : $base"
