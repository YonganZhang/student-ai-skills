# Runtime Facts 单一真源协议(COL5)

## 类层问题(为什么所有项目都需要)

任何有"运行态"的项目(服务/pipeline/训练任务)都有一批**运行态事实**:
端口、活 log 路径、进程怎么重启、配置哪份是 runtime 真源、数据库 vs 配置文件谁说了算。

这些事实的天然下场是**散在各 rule 的注释/skill 正文/AI 记忆里**,且环境一变(重启方式改了、
log 换路径)就全员过时 → AI 按过期路径排查、等待不再写入的 log,或改了运行时根本不读的配置。

## 协议(硬规则)

🔴 **每个有运行态的项目,`_fs/manifest.yml` 必须有 `runtime_facts:` 节** — 运行态事实的唯一登记处。
🔴 **rules / skills / 脚本注释只链不抄**:写"详 manifest.yml runtime_facts",不复制具体路径/端口
   (抄一份 = 漂移源;这正是低漂移列"目录即索引"原则在运行态上的对应物)。
🔴 **谁踩坑谁更新**:发现 manifest 与实际不符,当场更新(同 upstream-first 的 cheatsheet 纪律),
   并在条目上留一行 `# 🔴 <date> 纠错:...` 让后人知道曾经错过什么。

## Schema(按需取节,别硬凑)

```yaml
runtime_facts:
  service:
    start: "<启动命令或脚本路径>"
    stop: "<杀进程方式>"
    port: <端口>
    health: "<探活命令>"
  logs:
    live: "<活 log 路径(唯一可信)>"
    stale_traps:            # 已知的假 log(别再踩)
      - path: /tmp/xxx.log
        why: "旧启动方式残留,服务重启后不再写入"
  truth_owners:             # "X 的 runtime 真源是谁"对照表(防改死配置)
    - fact: "<某类配置,如 persona>"
      owner: "<真源,如 data/data_v4.db personas 表>"
      not: "<容易误改的死配置,如 cmd_config.json persona[]>"
  env: "<运行环境绝对路径,如 .venv/bin/python>"
```

## 消费方

- AI 进项目排查运行态问题(log 在哪/怎么重启/改哪份配置)→ **第一动作读本节**,不靠记忆/grep 猜。
- `topic-doctor` 后续可加检查:software mode 项目缺 `runtime_facts:` 节 → warn(渐进,先规范后检测)。

## 反例(示例)

- 🔴 同一服务有多个 log 路径并存(旧启动方式留下的 stale log、指错的软链、真正在写的 log),
  脚本等待 stale log 里的阶段信号 → 一直卡到超时。`stale_traps` 就是为了把这类假 log 显式登记。
- 🔴 配置文件里有一份看似真源的字段,但运行时实际读数据库 → AI 改了文件、重启后"没生效"。
  `truth_owners` 的 `not:` 字段就是为了把这类死配置显式登记。
