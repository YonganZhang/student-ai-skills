# 详细 SOP：正确集成候选有效组件（mlgain-integrate-component）

> 定位：本页保留原 mlgain 技能正文作为阶段表、场景路由与自检清单。步骤选择以 [Auto Research 组件工作流](../../share-autoresearch-engine/references/component-integration.md) 为唯一执行入口；两者冲突时以组件工作流为准（例如：受控比较细则、HPO 与分布式探针只在对应阶段/实际使用时适用，不作为每次试模块的前置门）。本页里的 `references/…`、`scripts/…`、`assets/…` 均指本技能目录下的文件。

背景：AI 帮忙提升模型指标时最常见的真实失败模式，不是"防作弊"这类流程问题，而是三类具体的技术失误：① agent 从零重写 data/training pipeline 引入 subtle bug；② 组件"接得对不对"和"接得合不合理"没有分开判断，随手接、随手判断有没有用；③ 集成没达到预期时，AI 靠猜（"可能是数据问题"）而不是去看梯度/激活等内部信号。本 skill 是这三类失误的对应解法，2026-08-29 经三轮独立 Workflow 调研 + 一次 Codex 独立技术复核共同验证。

**明确定位**：这里教的是知识和感知力，不是限制。不做 sealed audit、查询预算这类"防作弊"机制——主流大模型本身已有不做学术造假的准则，额外加这层是限制能力，不是补能力。

## 严谨程度按用途分级——不许用这套 SOP 当理由拖延或拒绝给结论

**S0 立项时先确认一句话：这次是为了发论文/一次性证明某个改动有优势，还是要建一套长期维护、别人也会复用的生产 pipeline？** 没问清楚就默认按"论文/一次性"这一档走，因为这是更常见的场景，不要反过来默认最重的那一档。

| | 论文 / 一次性证明优势（默认档）| 生产 / 长期维护（需用户明确要求才升级）|
|---|---|---|
| Wiring Gate（P0/P1/P2/P10）| **必做**，几秒钟的事，不做等于都没法确认模块真的接上了 | 必做 |
| 单变量消融 + 多 seed | **必做**，但 3–5 个 seed、常识判断"是不是噪声"就够，不需要严格的方差带统计检验 | 全套：预注册 seed 数、方差带、采纳门 |
| nuisance 超参重调 | 两个 arm 都用**合理的默认超参**跑一遍即可，不需要给新架构单独开一轮完整 HPO；如果心里没底就明说"两边超参没有分别调优，这是一个已知局限" | 两个 arm 各自独立调参到最优 |
| 借现成 pipeline（P0-P5）| 如果手头已经有能跑、你也信得过的代码，**直接跳过**，不需要为了走流程去找/换一个"更正规"的包 | 建议走，尤其要长期维护时 |
| 分布式探针（P14-P22）| 单卡实验直接跳过 | 多卡训练时必做 |
| Method Card 报告（S11）| 几行话记清楚"改了什么、消融结果、seed 是哪几个"就够，不需要填满整张模板 | 建议填满，方便别人复用 |
| 理论放置判断（S4）/ 分类归档（S2）| 花一两句话确认"这个模块的假设和我的数据结构没有明显冲突"即可，不需要展开长篇分析 | 建议按分类卡完整走一遍，方便未来新模块归档参考 |

**anti-overcaution 铁律**：以上探针、阈值、SOP 步骤全部是**诊断工具**，不是**审批关卡**。用户目标是发论文/一次性证明优势时：
- 不许以"还没做分布式验证""还没重调超参""还没借更正规的 pipeline"这类跟当前目标无关的理由拒绝给出结论、拖慢进度、或反复要求用户先补更多验证。
- 探针读数（比如 update:weight 不在 1e-3 附近）是**要报告给用户的信息**，不是**AI 自己就能拿来否决继续往下做的理由**——数字给出来、说清楚意味着什么，要不要为此多花时间验证，决定权在用户，不在 AI。
- 只有一种情况例外：**Wiring Gate 没过**（模块根本没接进图里、梯度不通）。这个不分场景，必须先修，因为继续跑下去产出的任何数字都是废的，这不是"过度谨慎"，是"这组数字目前没有意义"。

## 核心原则

1. **不重写别人已经写对的 pipeline**。从零搭 data loading/窗口切分/归一化反变换/训练循环，是 agent 引入 silent bug 的最高发区，且这类 bug 会伪装成"这个模块没用"。默认借一条官方/可信包的现成 pipeline，只换模型定义，借来后先证明它本身接对了，才允许换模型。
2. **惯例优先于发明**：宿主框架/生态已有的插槽定义、注册表、放置默认值，一律直接采纳；确实没有对应插槽时才允许自定义，且要显式记录"这是自定义扩展"。
3. **分类先于放置**：任何组件写代码前先按 `module-taxonomy.md` 的分类卡定型，分类结果直接决定合法插入点和必查失败模式。
4. **契约与理论依据来自源码/论文，不来自记忆**。
5. **"讲得通→接得对→有没有用"三个递进问题，顺序不可颠倒**：先理论放置判断，再机械接线验证，最后才是效果对比。
6. **测量先于归因**：集成没达到预期时，不许说"可能是数据/模型问题"这类话，必须先跑 `mechanistic-diagnosis.md` 的探针拿到具体数字。
7. **一次只集成一个组件，做消融时只改这一个变量**；nuisance 超参（LR/warmup/正则）要在两个 arm 内各自重调，否则测的是"旧超参多适合旧架构"，不是消融。参数量/训练时间的变化不需要控制，但要记录。
8. 优化器/调度/训练循环类改动永远不能与架构改动同轮引入。训练循环框架选择走 `pipeline-package-catalog.md` 的 Tier A/B/C 判别测试（自己写循环才强制用 Lightning；包本身自带经过验证的训练循环就保留原生循环），不是 Lightning/Ignite/fastai 三选一。
9. 经三轮 Codex+Workflow 联合审计 + 多轮真实合成实验/真实环境执行验证：本 skill 覆盖单机 PyTorch、时序预测/分类/异常检测/插补、主流 CV 任务已有较高把握。**`torch.compile` 已核验并落为 `mechanistic-diagnosis.md` 工具备注的专条**（结论：hook 在 compile 之前注册完全可用且数值与 eager 一致；之后注册则静默失效，`instrument()` 已加前置门拦截，且该门已修复为逐子模块检查，不再只查顶层）。**LLM+PEFT 生态与图神经网络 pipeline 已补进 `pipeline-package-catalog.md` 的 L1/G1 行，两行均已于 2026-08-29 在本机隔离 venv 实测执行**（实测中推翻了一条源码核验得出的结论：`PretrainedConfig` 仍是活别名，不会 ImportError；也发现了 `SFTConfig` 默认值会让自定义架构从零训练直接崩、peft 0.20.0 两处 API 漂移、PyG 两处错误机制描述）。原列出的四条未核验项：①`torch.compile`×FSDP/DDP交互——已实测（FSDP1下P16与compile门均正确，但发现两条新硬约束：`fullgraph=True`+FSDP1即使零hook也崩、compile在FSDP包裹前逐层做会硬崩，另有一条新静默盲区：`summon_full_params`内外的参数FQN完全不相交）；②`fullgraph=True`下hook去向——已实测，原来的"二选一"问法本身错了，实际按hook类型+注册顺序分叉（backward hook提前注册会被响亮拒绝，forward hook提前注册正常工作且与eager逐位相同，任何hook事后注册都静默丢弃）；③手写`torch.cuda.CUDAGraph`捕获——已实测，且推翻了旧文本"会被RuntimeError拦住不需要额外防护"的说法（这条只对`torch.compile(mode="reduce-overhead")`成立，对手写capture是反的：hook只在capture那刻触发一次，之后每次replay都可能静默读到同一块显存的旧值，已在`instrument()`加`is_current_stream_capturing()`守卫并写入`mechanistic-diagnosis.md`的S-17）。**仍未核验**：④HF transformers 模型在 `torch.compile` 下的 hook 行为（本轮只实测了裸 `nn.Module`）；⑤ FSDP2（`fully_shard`）下 P16 与 compile 门的行为（本轮只实测 FSDP1）。遇到这两类时按元规则（M1-M8）自行归档，不要假设已覆盖。
10. **`scripts/probe_hooks.py` 和 `assets/pytorch-component-socket.py` 里的每一个函数都跑过真实的合成实验验证**（不是只做过语法检查），三轮验证累计发现并修复了11个真实代码bug（详见各文件changelog风格的docstring和本文件changelog）。前5个（round 1-2）：`instrument()`对torch.compile和函数式激活(`F.relu`)的静默盲区、`diff_stats()`的epsilon地板会反转梯度消失场景的排名、`sgd_update_proxy()`/`measure_real_update()`对零初始化参数报出天文数字、`ComponentSocket`的REPLACE模式曾会执行base_path产生副作用。后6个（round 3，对抗性hostile-input搜索+真实CUDA-graph/compile执行发现）：**#6** `diff_stats()`对NaN/Inf的处理会把整层坍缩成NaN的模块静默排到排名末尾而不是最前（`math.log(nan)`不报错、Python排序对NaN比较全为False）；**#7** `ComponentSocket`的RESIDUAL模式先检查`z.shape==base.shape`再套`scale`，`scale`广播出的shape从未被检查，0维base+多通道scale能在契约检查全绿的情况下悄悄改变输出shape；**#8** `check_contract()`只让`base_path`进`eval()`（candidate里的BatchNorm仍会被forward更新running stats）、用`.train(was_training)`整体恢复（会误唤醒base_path内部本应保持冻结的子模块）、且不保存/恢复RNG状态（同seed下会被Dropout悄悄污染，实测divergence达3.4741）；**#9** 三个零初始化探针函数对拼错的参数名返回"看起来健康/看起来确诊"的假结果而不是报错；**#10** `instrument()`的compile guard原来只查模型顶层，子模块级`torch.compile`能绕过去、返回一个非空但残缺的stats dict；**#11** hook在CUDA graph手写capture期间没有守卫，capture后每次replay都可能读到同一块显存的旧值而不报任何错误。**这些bug已全部修复并通过直接执行重新验证，但这提醒一件事**：这套代码是本地设计，不是引用一个久经考验的第三方库，三轮验证下来bug特征已经从"核心数值逻辑"转向"对抗性输入/状态泄漏/守卫覆盖范围"，这是正在接近饱和的信号但不是"已经排除干净"的信号——遇到本文档未覆盖的边界情况时，先怀疑代码可能有类似的"退化输入下静默返回合法但错误的数字"的问题，不要默认它绝对正确。

模块接入的 S8 检查须按 [ARIS 接入检查](../../share-autoresearch-engine/references/aris/integration-checks.md) 落成真实项目断言并保存执行日志；通过后独立审查再扩大实验。完整 ARIS 技能包见 [本地工作流](../../share-autoresearch-engine/references/aris/README.md)，保留本技能的接口与机理探针。

## 固定 SOP（S0 起步前先看 P0 是否要借 pipeline）

```
P0 借用现成 pipeline(可跳过,若项目已有验证过的 pipeline)
  P0选包 → P1 install/vendor → P2 数据格式适配 → P3 定位swap点
  → P4 证明借来的pipeline本身接对了(golden run + 冒名顶替测试)
  → P5 换入候选模型,回到 S0
↓
S0 立项与预期声明 → S1 惯例定位 → S2 分类归档 → S3 契约抠取(宿主swap契约若走过P0,否则只做候选组件)
→ S4 理论放置判断 → S5 兼容性检查 → S6 数据合理性 → S7 集成编码
→ S8 Wiring Gate(接线门禁)（若最终要多卡训练：单卡Wiring Gate全绿后,scale-up之前必须过P14/P15/P17/P22分布式闸门）→ S9 受控比较
  →【未达预期?】→ S10 机理诊断(强制,回S8)→ S11 归档报告
```

## 场景路由表

| 阶段 | 场景 | 读这个 |
|---|---|---|
| 动手写 pipeline 代码之前 | 需要完整 data→train→eval pipeline，项目里没有或是自己从零搭的 | `references/borrow-existing-pipeline.md` |
| P0 选包 / P3 定位 swap 点 | 按领域查已核验的包和精确 swap 机制（含已排除清单） | `references/pipeline-package-catalog.md` |
| S1 定位插槽 | 宿主框架/生态已规定这类模块接在哪 | `references/framework-placement-conventions.md` |
| S2 归档分类 | 这是什么模块？合法插入点、必查失败模式、必跑探针 | `references/module-taxonomy.md` |
| S2 遇到全新模块 | 不属于任何已知家族，怎么归档而不是重新发明 | `module-taxonomy.md` 的「元规则 M1–M7」 |
| S3 抠契约 | 源码/论文抠真实契约 + 逐层等价性验证阶梯 | `references/extract-interface-contract.md` |
| S4 理论判断 | 归纳偏置匹不匹配、位置的理论依据 | `references/architecture-placement-theory.md` |
| S5 兼容性 | 通用五条 + 族专属兼容标记 + 构造期 assert | `references/compatibility-check.md` |
| S6 数据 | Karpathy 五步 + 两个验证集 + 迷路重置程序 | `references/feature-and-data-reasonableness.md` |
| S7 集成编码：函数保持的插座协议 | 硬旁路/零贡献/可训练对照/真组件四层验证，而不是"占位物分数不变"这种不严格判据 | `references/function-preserving-socket-protocol.md` |
| S7 集成编码：残差/门控安全接入 | 什么时候该用 ReZero/LayerScale/门控残差做默认接法，什么时候不该用 | `references/residual-gating-safe-integration.md` |
| S8 接线证明 | 机械门禁：接对了没有（不管准不准），含借用 pipeline 场景的冒名顶替测试 | `references/integration-sanity-checks.md` |
| S9 受控比较 | 单变量 + nuisance 重调 + 方差带 + 采纳门 | `references/controlled-comparison.md` |
| **S10 没达到预期** | **不许猜：症状→探针→读数→动作** | `references/mechanistic-diagnosis.md`（配 `scripts/probe_hooks.py`） |
| S11 归档 | Method Card 式报告，含分类卡、探针数字、pipeline 来源 | `references/integration-report-template.md` |

## 快速自检

- [ ] 这条 pipeline 是借来的还是自己从零写的？如果是自己写的，为什么不借？
- [ ] 借来的 pipeline 用它原装模型跑通过 golden run、冒名顶替测试了吗？
- [ ] S1：查过宿主生态对这类模块有没有既定放置了吗？
- [ ] S2：分类卡填完了吗？必跑探针清单是什么？
- [ ] S7：用的是硬旁路/零贡献/可训练对照哪一层验证？残差合并是不是仅对同形状加性修正类组件默认开启？
- [ ] S8：Wiring Gate 全绿了吗？数字记下来了吗？（注意：ReZero/LoRA 类零初始化技术首步核心参数梯度为 0 是正常的，不是接线错误）
- [ ] S9：nuisance 超参在两个 arm 里各自重调了吗？baseline 的 seed 方差带量出来了吗？
- [ ] 目标是多卡吗？P14（跨rank参数发散）跑了吗？分片后端下 P3/P7/P13 是经 P16 取的数还是直接读的 `.grad`？
