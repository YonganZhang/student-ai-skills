# Migration Tools — old TOP upgrade helpers

> 一次性迁移工具。**使用频率非常低**(每次 v 大版本升级才用一次)。
> **没有触发词,需要时专门让 AI 搜本目录**。

## 工具清单

### `rename_wiki_to_underscore.py`

把五合一 wiki(无 `_` 前缀的老版本)升级到 v4 新版本(全 `_` 开头)。

**核心动作**:
- `wiki-methodology/` → `_wiki-methodology/`
- 内部所有 .md / .yml / 子目录加 `_` 前缀
- 所有 `[[wikilink]]` 同步加 `_`
- 所有 `[text](path/xxx.md)` markdown 链接同步
- 项目内代码 / skill / config 的外部引用同步

**用法**:
```bash
# Mode B(完整版,默认):内部 + 顶级目录 + 外部引用
python rename_wiki_to_underscore.py --root <project_dir>

# Mode A:只改内部,不动顶级目录
python rename_wiki_to_underscore.py --root <project_dir> --mode A

# Mode C:轻量版,只改 6 个顶级 index 文件
python rename_wiki_to_underscore.py --root <project_dir> --mode C

# dry-run:只看会改啥,不实际改
python rename_wiki_to_underscore.py --root <project_dir> --dry-run
```

**安全**:
- 改名前**沙盒 cp 验证**:`cp -r wiki-methodology /tmp/sandbox/ && python ... --root /tmp/sandbox`
- 验证 link 无残留:`grep -rE '\[\[[^_]' _wiki-methodology/ | head`(应只剩 bash `[[` 不是 wikilink)
- 改名后跑 `_code/lint.py` 检查
- 改名后跑 `_code/sync_wiki.py` 验证联动

**复用**:
- 跨项目通用,只依赖 `wiki-methodology` 目录名(可改 `WIKI_DIR_NAME` 常量)
- 跟项目 `_code/migration/` 同源(本目录是 SSOT,各项目 copy 一份用)

## 触发(用户专门搜来用)

- "五合一升级到 v4"
- "把 wiki 全改成 _ 开头"
- "migrate wiki-methodology 到新版本"
- "老 wiki 升级"

**不会被普通 prompt 触发**(故意的)。

版本历史见 `share-top/references/changelog.md`。
