# journey-runner：自驱检测架构的观测层与易踩点

用途：搭建或改造配置化 journey pipeline（runner / observer / steps / journeys yaml）时读。铁律本身见入口 §6。

参考实现(示例):某项目的 `_tests/e2e/journey/`(runner.py + observer.py + steps/*.py + journeys/*.yaml;私有项目,未随本包发布)。它把"AI 操作/测试浏览器"固化成**可增删流程的配置化 pipeline**。

## 6.2 观测层(自驱检测的眼睛)

- **DOM 弹窗**:`page.add_init_script` 注入 MutationObserver + `expose_binding` 实时推 Python(选择器 + 文本兜底双判),弹窗一出现就进事件流。
- **网络 in/out**:`page.on("request"/"response")` 抓发给 MCP 的 brief body(输入)+ MCP 返回的 job/校验/错误(输出)。
- **关键洞**:只挂 page 钩子 → 手动 API/curl 触发的构建**进不了事件流** → 结构上不可能假完成。
- 全部落 `events.jsonl`,步骤断言用 `popups_since(ts)` / `responses(url, since)` / `requests(url, since)` 查。

## 6.3 已知易踩

1. **弹窗锚点要早于点击**:`t_gate = time.time()` 必须设在第一次点击之前 —— repair 窗可能在 proceed/tier 阶段就弹,锚点晚了会漏。
2. **正则不裸子串**:`error`/`invalid` 用词边界 `\b`,补中文动词,否则误报。
3. **0 张图要判失败**:`broken == []` 在零图时假阳过 → 必须 `total > 0`(非 refine tab)。
4. **关键步失败要段内中止**:不只段间,for-loop 顶部也检查 `_aborted`,别在坏前提上空跑 50min。
5. **只读 JSON body**:`on_response` 跳过 SSE/流式/二进制(读流会阻塞 sync response 线程),按 content-type 判。
