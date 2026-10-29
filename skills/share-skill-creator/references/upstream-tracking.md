# 上游跟踪：UPSTREAM.json

吸收、复制或改写外部 skill 内容时，在该 skill 根目录写一份 `UPSTREAM.json`，作为上游来源的唯一记录。文件头注释、`upstream-source.md` 等可以保留作说明，但版本与路径以本文件为准。

## 格式（schema `skill-upstream/v1`）

```json
{
  "schema": "skill-upstream/v1",
  "sources": [
    {
      "repo": "owner/name",
      "paths": ["skills/foo/SKILL.md"],
      "absorbed_commit": "40 位 commit sha",
      "absorbed_at": "YYYY-MM-DD",
      "mode": "vendored",
      "local_paths": ["references/UPSTREAM-SKILL.md"],
      "watch": true,
      "note": "",
      "license": "MIT"
    }
  ]
}
```

| 字段 | 含义 |
|---|---|
| `repo` | GitHub `owner/name` |
| `paths` | 我们吸收的上游路径（文件或目录，相对上游仓库根） |
| `absorbed_commit` | 吸收时依据的上游 commit；查不到时按吸收日期反推：`gh api "repos/<o>/<r>/commits?path=<p>&until=<date>T23:59:59Z&per_page=1"`，并在 `note` 写“按日期反推” |
| `absorbed_at` | 吸收或最近一次选择性同步的日期 |
| `mode` | `vendored` = 逐字复制，`paths` 与 `local_paths` 必须一一对应且都是文件；`semantic` = 改写吸收，路径可以是目录、数量可以不同 |
| `local_paths` | 本地对应文件，相对本 `UPSTREAM.json` 所在目录，必须存在 |
| `watch` | 是否纳入定时上游检查 |
| `note` | 本地改动、例外、旧记录文件的位置等；没有就写空串 |
| `license` | 可选，上游许可 |

一个 skill 吸收多个上游、或同一上游不同批次时，`sources` 写多项。只改了 frontmatter 的逐字副本仍记 `vendored`，在 `note` 说明本地改了什么；改写过正文的记 `semantic`。

## 项目安装记录

`UPSTREAM.json` 跟踪模块源库吸收的上游，不代表每个项目实际安装的版本。可选模块启用后按 [模块生命周期](placement-and-modules.md) 在项目保存实际来源 commit、适配身份和安装文件指纹；与声明安装版本核验，最新版仅作升级提示。安装回执不是第二份项目进度，也不承担安全签名。

## 什么时候写、什么时候改

- 吸收外部内容（absorber Phase 4）时同步写入；只写文件头注释不算完成登记。
- 按上游更新做选择性同步后，更新 `absorbed_commit` 与 `absorbed_at`，并在 `note` 记下没有采纳的上游改动及原因。
- 上游改名或搬路径时，改 `paths` 指向新路径，`note` 写旧路径。

## 检查

```bash
python3 ~/.claude/skills/share-skill-creator/scripts/upstream_watch.py --lint     # 离线格式检查
python3 ~/.claude/skills/share-skill-creator/scripts/upstream_watch.py --remote   # 查上游变化（只读）
```

`--remote` 对 `watch: true` 的每个来源，查吸收 commit 之后是否有触及 `paths` 的上游提交；`vendored` 还会比较上游当前文件与本地文件的 sha256，内容一致就不报。只输出确有变化的路径和失败项（每次 gh 调用 20 秒超时，失败不重试）。它不修改任何 skill：看到变化后按 absorber 流程人工判断是否吸收。

需要定时检查时，用 cron 等自行定时运行 `--remote --report <文件>`。
