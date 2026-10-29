# 何时用 Skill,何时改 Persona Prompt(跨项目通用决策)

## 反模式（永远不许）

🔴 **把"用户引导 / 测试用例 / 能力清单 / SOP / 项目介绍 / FAQ / 数据格式说明 / 接入文档"硬塞进 persona system_prompt**

理由(钉死):
- prompt 越塞越长 → 默认上下文消耗 / token 浪费(每次调用都付钱)
- 不分层(用户可见 vs 内部实现混一起)→ 商业秘密泄露风险
- 改一处必改 prompt + reload Persona → 每次小更新都成 commit
- 跨 Persona 不能复用(同一段内容不同 Persona 各塞一份 → 漂移)
- 用户(非开发者)不能改 → 维护壁垒

## 正解:走 Skill 系统(progressive disclosure)

### 决策树(每次"加 X" 必走)

```
有人问"加 X" → 第一步先判定 X 是什么:

X = "用户引导 / 测试用例 / 能力总览 / SOP / FAQ / 数据格式 / 接入文档 / 学生 onboarding"
  → 🟢 走 skills/<x>/SKILL.md(新建)+ persona.skills 加入
  → 🔴 禁:写到 persona system_prompt

X = "身份(我是谁)/ 行为基线(永远走专家委派 / 不绕过)"
  → 🟢 写 persona system_prompt(只这两类合法)
  → 判断:prompt 里出现身份/行为基线以外的段落,或长度随每次需求持续增长 → 说明又在塞内容,review

X = "能力 / 工具 / 算法 / 接口 / 模型"
  → 🟢 插件工具 / 服务端工具(按项目的工具接入规范)
  → 🔴 禁:写到 prompt 描述能力(LLM 看 tool schema 即可,不需 prompt 重述)

X = "商业秘密 / 算法实现"
  → 🟢 留在项目内部代码(插件 / 服务端实现)
  → 🔴 禁:LLM 能"看到"任何内部实现细节(包括 prompt 里间接描述)
```

### 自检触发器(写 persona prompt 前必走)

```
1. 我打算往 persona prompt 加的内容,是"身份 + 行为基线"两类吗?
   - 是 → ✓ 继续
   - 否 → 🔴 STOP,改成 skills/<x>/SKILL.md

2. 加完后 prompt 里是否出现了身份/行为基线以外的段落(引导、案例、FAQ、格式说明)?
   - 否 → ✓
   - 是 → 🟡 警告,大概率又在塞内容,review

3. 这内容跨 Persona 复用吗?
   - 是 → 🔴 必走 Skill(prompt 复制 = 漂移)
   - 否 → ✓ 继续
```

## 可选:项目级提示检查模板(仅在用户要求启用 hook 时)

项目已有提示词检查 hook 时,可加一类 trigger(示例):

```bash
# trigger:涉及 persona prompt 修改
if echo "$PROMPT" | grep -qiE 'persona.*prompt|system_prompt|改人格|提示词|加引导|加介绍|加说明|让.*知道|让.*能解释'; then
cat <<'EOF'

🔴 检测到"persona prompt / 系统提示词" 关键词 — 立刻自检:
1. 我打算加的内容是"身份 / 行为基线"两类吗?(只这两类合法)
2. 不是 → 改成 `skills/<x>/SKILL.md` 走 progressive disclosure
3. 反模式:测试引导 / 介绍 / SOP / 能力清单 / FAQ → **必走 Skill,不糊 prompt**
EOF
fi
```

## 何时此规则不适用

- 项目**不用**支持按需加载 Skill 的 agent 框架 → 本规则不适用,但仍可用 system message 文件分层(类比)
- LLM 客户端不支持"按需加载文档" → fall back 到 prompt 必要,但仍要分层(把内容拆 system message + 引用 file)

## 反例(示例)

- 把"测试引导的几个场景"写进 persona system_prompt → prompt 越来越长,每次调用都付费,改一处要 reload persona。
  正确做法:场景移到一个按需加载的 skill,persona 只保留身份与行为基线;验收时真问一次"怎么测",确认回答引用了 skill 内容。

## 关联

- 具体框架的 Skill 协议、per-persona 挂载方式,记在各项目自己的 wiki / 上游资料里,不在本文复制。
