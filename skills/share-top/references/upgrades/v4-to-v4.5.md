# v4 → v4.5 增量升级(项目已是 v4 时的统一升级路径)

> 用户说"把六合一升级到最新 / 升级 v4.5 / 项目架构升级"且项目已有 v4 骨架时走这里。
> 老项目(v3/五合一/TOP.md)不走这里 → `share-top-upgrade-old`。
> 一句话:**升级不是重排目录,是"跑诊断 → 按 next_hint 清零"** —— v4.5 的检测器已经知道缺什么,别即兴发挥。

## 步骤(幂等,可重复跑;每步都有验收)

1. **诊断**:跑 `python3 ~/.claude/skills/share-top/scripts/sixone-cli.py brief .`(或 `topic-brief.py .`),读 `codebook` / `gates` / `next_hint` 字段;再 `sixone-cli.py doctor .` 看 verdict。下面只补它们报缺的,不动没报的。
2. **gates manifest 缺**(`gates: missing`):
   cp `templates/v4-architecture/_wiki-methodology/_tests/_gates.yml` 到项目同位置,填 1-2 个**真 gate**(项目已有的可跑校验命令,如 `run_pipeline <name> --validate` / `pytest -q`)。
   🔴 每个 cmd 必须**实测 exit0 通过后**才登记 —— 写一个没跑过的 gate = 空壳,比没有更糟。
3. **无 `_codebook/`**:给主 pipeline 写第一个域节点(schema + 树协议 → `templates/codebook/_node_schema.md`;用户视角自顶而下,正文一屏内),写完**必跑** `sixone-cli.py deposit` 盖章。≥2 节点时补 `_index.md`(TOC,不盖章)。单 pipeline 项目一个节点就是合法终态,不强迫长树。
4. **codemap 接线**:`_codemap.md` 防混乱入口表加一行指 `_codebook/`(寻路靠 book、核实靠代码图谱;参照 SKILL.md CodeBook 节)。
5. **有旧 `_codemaps/`**(老 Scan 产物):用户可见系统/模块并入 `_codebook/<域>.md` 并盖章;纯结构事实(依赖边/调用图)删除不迁(live query codegraph);空目录归档项目 `_legacy/`。
6. **test 引用统一**:CodeBook/registry 里的 `test:<id>` 改指 `_gates.yml` 的 gate id。
7. **验收**:`topic_doctor` verdict ∈ {ok, warn}(无 block);`topic_brief` 的 `next_hint` 不再指升级缺口;改过 `_codebook/*.md` 的全部 fresh。

## 明确不做

- 不为升级动 `raw/` 数据、LOCK 产物、论文正本(项目不变约束优先)。
- profile 为 `mini` / `admin` / `collection` / `archive` / `upstream-wrapper` 的项目不强制本清单(doctor 也不会催)。
- 不重写已有的好文档;升级只补缺口,不搬家。

## 对话层 FAQ(用户常问)

- **要重启对话吗?** 不用:技能/脚本 全是磁盘现读,已生效。sixone 当前走 CLI；老对话照常干活,自然换代。
- **老对话行为还按旧规矩?** 那是上下文残留记忆,说一句"重读 share-top SKILL.md"即可,不用重启。
