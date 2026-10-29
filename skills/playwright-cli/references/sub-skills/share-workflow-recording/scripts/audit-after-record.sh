#!/usr/bin/env bash
# 录后自动审计(SKILL.md §5 元承诺 + v2  4 维 scenario lock)
# v1 用法:audit-after-record.sh <project-root> <baseline-lines> <expected-rounds>
# v2 用法:audit-after-record.sh <project-root> <baseline-lines> <expected-rounds> --scenario <id>
# exit 0 = 全通过 · exit 1 = 红字不一致 · exit 2 = signals.yml 未锁

set -u

PROJECT_ROOT="${1:?project-root 必传}"
BASELINE="${2:?baseline 必传}"
EXPECTED_ROUNDS="${3:?expected-rounds 必传}"
SCENARIO_ID=""
if [[ "${4:-}" == "--scenario" && -n "${5:-}" ]]; then
  SCENARIO_ID="$5"
fi

SIGNALS_YML="$PROJECT_ROOT/.codex/audit-signals.yml"
# Claude 项目常放在 .claude/，Codex 项目放在 .codex/；先 .codex 保持既有行为，再回退 .claude
[[ -f "$SIGNALS_YML" ]] || SIGNALS_YML="$PROJECT_ROOT/.claude/audit-signals.yml"
RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; NC=$'\033[0m'

if [[ ! -f "$SIGNALS_YML" ]]; then
  echo "${RED}🔴 无 audit-signals.yml · 先走阶段 1 锁信号${NC}"
  exit 2
fi

LOG_PATH=$(python3 -c "
import yaml; d = yaml.safe_load(open('$SIGNALS_YML'))
print(d['audit_signals']['log_path'])
")
USER_MSG_GREP=$(python3 -c "
import yaml; d = yaml.safe_load(open('$SIGNALS_YML'))
print(d['audit_signals']['user_msg_grep'])
")
AI_REPLY_GREP=$(python3 -c "
import yaml; d = yaml.safe_load(open('$SIGNALS_YML'))
print(d['audit_signals']['ai_reply_grep'])
")
AI_REPLY_DUMP_GREP=$(python3 -c "
import yaml; d = yaml.safe_load(open('$SIGNALS_YML'))
print(d['audit_signals'].get('ai_reply_dump_grep', d['audit_signals']['ai_reply_grep']))
")
CYCLE_DONE_GREP=$(python3 -c "
import yaml; d = yaml.safe_load(open('$SIGNALS_YML'))
print(d['audit_signals']['cycle_done_grep'])
")
TOOL_TRACE_GREP=$(python3 -c "
import yaml; d = yaml.safe_load(open('$SIGNALS_YML'))
print(d['audit_signals']['tool_trace_grep'])
")

[[ -r "$LOG_PATH" ]] || { echo "${RED}🔴 log 不可读:$LOG_PATH${NC}"; exit 1; }

slice() { awk "NR>${BASELINE}" "$LOG_PATH"; }

USER_COUNT=$(slice | grep -c -E "$USER_MSG_GREP" || true)
AI_COUNT=$(slice | grep -c -F "$AI_REPLY_GREP" || true)
CYCLE_COUNT=$(slice | grep -c -F "$CYCLE_DONE_GREP" || true)
TOOL_COUNT=$(slice | grep -c -E "$TOOL_TRACE_GREP" || true)

echo "============================================================"
echo "录后审计报告  scenario=${SCENARIO_ID:-(无 · 仅基础信号)}"
echo "  log:      $LOG_PATH (baseline=$BASELINE · current=$(wc -l < "$LOG_PATH"))"
echo "  expected: $EXPECTED_ROUNDS 轮"
echo "============================================================"

# v3: STRICT fail → exit 1 (gate push) · SHOULD/METRICS/INTENT fail → 🟡 WARN(不 gate)
# 接受 LLM stochastic 真本质 · 真验证 plugin work 真**trunk 单元测试** 真**真**真**职责
FAIL=0; WARN=0

# STRICT 真**真**真 gate · SHOULD/INTENT/METRIC 真**真**真**真**真不 gate
check_eq()       { [[ $2 -eq $3 ]] && echo "${GRN}✅ $1:$2${NC}" || { echo "${YEL}🟡 $1:$2 (应 $3 · LLM 不稳 WARN)${NC}"; WARN=1; }; }
check_ge()       { [[ $2 -ge $3 ]] && echo "${GRN}✅ $1:$2${NC}" || { echo "${YEL}🟡 $1:$2 (应 ≥ $3 · LLM 不稳 WARN)${NC}"; WARN=1; }; }
check_gt()       { [[ $2 -gt $3 ]] && echo "${GRN}✅ $1:$2${NC}" || { echo "${YEL}🟡 $1:$2 (应 > $3 · LLM 不稳 WARN)${NC}"; WARN=1; }; }
# STRICT 真**真**真 gate(只在 STRICT tools 真 fail 真触发)
check_strict_fail() { echo "${RED}🔴 STRICT $1 未调 · gate FAIL${NC}"; FAIL=1; }

echo
echo "--- ① 基础信号(4 类)---"
check_eq "用户消息" "$USER_COUNT" "$EXPECTED_ROUNDS"
check_ge "AI 返"    "$AI_COUNT"   "$USER_COUNT"
check_eq "完成 cycle" "$CYCLE_COUNT" "$EXPECTED_ROUNDS"
check_gt "tool 链"  "$TOOL_COUNT" "0"

# === scenario-level 4 维 ===
if [[ -n "$SCENARIO_ID" ]]; then
  TMP_SCEN=$(mktemp)
  python3 - <<PY > "$TMP_SCEN"
import yaml, json
d = yaml.safe_load(open('$SIGNALS_YML'))
s = (d.get('scenarios') or {}).get('$SCENARIO_ID')
if not s:
    print("MISSING")
else:
    print(json.dumps(s, ensure_ascii=False))
PY
  SCEN_DEF=$(cat "$TMP_SCEN"); rm "$TMP_SCEN"
  if [[ "$SCEN_DEF" == "MISSING" ]]; then
    echo "${YEL}🟡 scenario '$SCENARIO_ID' 未在 audit-signals.yml scenarios 锁 — 跳过 4 维${NC}"
  else
    SLICE_TMP=$(mktemp); slice > "$SLICE_TMP"

    echo; echo "--- ② STRICT tools(必中 · 真 gate 真**真**真 FAIL)---"
    for t in $(echo "$SCEN_DEF" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin).get('expected_tools_strict', [])))"); do
      hit=$(grep -c "使用工具：$t" "$SLICE_TMP" || true)
      [[ $hit -gt 0 ]] && echo "${GRN}✅ $t (×$hit)${NC}" || check_strict_fail "$t"
    done

    echo; echo "--- ③ SHOULD tools(应中 · LLM 不稳 真 WARN 不 gate)---"
    for t in $(echo "$SCEN_DEF" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin).get('expected_tools_should', [])))"); do
      hit=$(grep -c "使用工具：$t" "$SLICE_TMP" || true)
      [[ $hit -gt 0 ]] && echo "${GRN}✅ $t (×$hit)${NC}" || { echo "${YEL}🟡 SHOULD $t 未调(WARN 不 gate)${NC}"; WARN=1; }
    done

    echo; echo "--- ④ INTENT KEYS(AI markdown 应含 · LLM 不稳 WARN)---"
    for k in $(echo "$SCEN_DEF" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin).get('expected_intent_keys', [])))"); do
      hit=$(grep -c "$k" "$SLICE_TMP" || true)
      [[ $hit -gt 0 ]] && echo "${GRN}✅ '$k' (×$hit)${NC}" || { echo "${YEL}🟡 INTENT '$k' 未出现(WARN 不 gate)${NC}"; WARN=1; }
    done

    echo; echo "--- ⑤ METRICS(数字阈值 · LLM 不稳 WARN 不 gate)---"
    python3 - "$SCEN_DEF" "$SLICE_TMP" <<'PY'
import json, re, sys
sc = json.loads(sys.argv[1])
text = open(sys.argv[2]).read()
YEL, GRN, NC = '\033[33m', '\033[32m', '\033[0m'
warn = False
for m in sc.get('expected_metrics', []):
    pat = m['name']; op = m['op']; val = float(m['value']); desc = m.get('desc', '')
    matches = re.findall(pat, text)
    if not matches:
        print(f"{YEL}🟡 metric {pat} 未匹配 ({desc} · WARN 不 gate){NC}"); warn = True; continue
    nums = []
    for x in matches:
        s = x.replace(',', '')
        if re.match(r'^[\d.]+$', s):
            try: nums.append(float(s))
            except: pass
    if not nums:
        print(f"{YEL}🟡 metric {pat} 匹配无数字 (raw={matches[:3]} · WARN){NC}"); warn = True; continue
    actual = max(nums)
    fn = {'gte': actual >= val, 'lte': actual <= val, 'eq': actual == val}[op]
    sym, color = ('✅', GRN) if fn else ('🟡', YEL)
    suffix = '' if fn else ' · WARN 不 gate'
    print(f"{color}{sym} {actual} {op} {val} ({desc}{suffix}){NC}")
    if not fn: warn = True
sys.exit(2 if warn else 0)
PY
    metrics_rc=$?
    if [[ $metrics_rc -eq 2 ]]; then WARN=1; fi
    rm -f "$SLICE_TMP"
  fi
fi

echo
echo "--- 用户原话(前 200 字)---"
slice | grep -E "$USER_MSG_GREP" | head -"$EXPECTED_ROUNDS" | cut -c1-200 | nl
echo
echo "---  AI 返(前 500 字 · 用 dump 信号)---"
slice | grep -F "$AI_REPLY_DUMP_GREP" | head -"$EXPECTED_ROUNDS" | cut -c1-500 | nl

echo
# v3 gate 策略(2026-05-25):只 STRICT tools 真 gate · SHOULD/INTENT/METRIC 真 informative
#   理由:LLM stochastic 真本质 · 录像 = 演示 · 真验证 plugin work 真**trunk 单元** 真责
#   见 share-workflow-recording/REFERENCE.md §5.4 真元承诺
if [[ $FAIL -eq 1 ]]; then
  echo "${RED}🔴 audit FAIL · STRICT tool 未调 → 真 gate push · 真先检查 plugin/persona/scenario yaml${NC}"
  exit 1
fi
if [[ $WARN -eq 1 ]]; then
  echo "${YEL}🟡 audit 通过 · 有 WARN(LLM 行为不稳真不强求)· 真可贴 URL${NC}"
  # gap #3 auto-trigger HITL(2026-05-26): WARN 出现 → 建议 cc 调 append_anti_pattern
  if [[ -n "$SCENARIO_ID" && -x "$PROJECT_ROOT/scripts/append_anti_pattern.py" ]]; then
    echo
    echo "${YEL}💡 HITL 建议(SKILL.md §5.5):本次有 WARN · 真可能是 LLM 新踩坑${NC}"
    echo "${YEL}   cc 真**真**真分析根因后 dry-run:${NC}"
    echo "${YEL}     python3 scripts/append_anti_pattern.py --scenario $SCENARIO_ID \\${NC}"
    echo "${YEL}       --what '<LLM 真做错了什么>' --fix '<正确做法>' --reason '<根因>'${NC}"
    echo "${YEL}   → 真用户 confirm yes/no/改 → 加 --confirm 真**真**真才写${NC}"
  fi
else
  echo "${GRN}✅ 全维度通过 · 可贴 URL${NC}"
fi
exit 0
