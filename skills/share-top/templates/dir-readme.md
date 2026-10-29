# <目录名>/ — <一句话说明这个目录是干什么的>

<!-- 目录 README 固定回答下面五个问题，每节 1~3 行，整份尽量 ≤25 行。
     不写改动历史（交给 Git）和文件间调用关系（交给 CodeGraph）：手抄的很快过时。
     理由见全局 rules/artifact-lifecycle.md「新建顶层目录时同时写 README」。 -->

## 放什么

<这里放哪类文件，例如：前端源码 / 清洗后数据 / 论文终稿图及其绘图脚本>

## 不放什么

<边界：哪些东西看着像但不属于这里，以及该放去哪，例如：临时下载 → `_tmp/`；试验代码 → `_sandbox/<日期>-<主题>/`>

## 入口

<先看哪个文件、怎么跑，例如：`src/main.ts`；`npm run dev`>

## 文件角色

<只写不明显的文件或子目录，一行一个；一眼能看懂的不写>

## 改动原因去哪查

`python3 ~/.claude/skills/share-top/scripts/sixone-cli.py record for-file <文件>`，或 `git log -- <文件>`。
