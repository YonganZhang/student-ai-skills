# CLI 技能验证样例

`forward-mdcount/` 保存独立 Claude 前向演练生成的只读目录统计工具及其行为测试，供以后修改技能时复跑。它与轻量母模板有不同的业务行为，不是全局命令，也不是第二份母模板。源码来源与创建时的工作区基线见样例 README。

在 `forward-mdcount/` 执行 `python3 -m unittest discover -s tests -v`。样例和测试源码追踪，缓存与临时输入不追踪。源码改动查 `git log -- skills/share-agent-cli/tests/`。
