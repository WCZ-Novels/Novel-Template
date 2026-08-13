# 小说存稿项目模板

## 依赖
- [VSCode](https://code.visualstudio.com/)
- [Noveler](https://marketplace.visualstudio.com/items?itemName=zerozawa.noveler)
- [Python](https://www.python.org/downloads/)

### 推荐安装
- [Color Highlight](https://marketplace.visualstudio.com/items?itemName=naumovs.color-highlight)
- [Rainbow CSV](https://marketplace.visualstudio.com/items?itemName=mechatroner.rainbow-csv)
- [Spreadsheet Viewer](https://marketplace.visualstudio.com/items?itemName=GrapeCity.gc-excelviewer)

## 功能
### 关键词高亮并提示
- 编辑[.noveler/config/](.noveler/config/)目录中CSV文件，在小说编辑时按`Alt+F`刷新词库，显示关键词高亮与提示信息。
- 在[.vscode/settings.json](.vscode/settings.json)中设置`noveler.confCSVFiles`属性，管理高亮CSV数据文件与高亮颜色。

### 敏感词检查
**功能基于[tencent-sensitive-words](https://github.com/FangCunWuChang/tencent-sensitive-words)**  

- `Ctrl+Shift+T`打开任务面板，选择“执行敏感词检查”或“执行敏感词检查（含单字）”，对非以`.`开头名称的目录内所有txt文件进行敏感词检查。
- 在[sensitive_words_whitelist.dic](.data/sensitive_words_whitelist.dic)中配置白名单词库，绕过默认词库中的敏感词；在[sensitive_words_extra_blacklist.dic](.data/sensitive_words_extra_blacklist.dic)中配置额外的黑名单词库。
- 敏感词检查结果自动同步至VS Code中“问题”列表。
- `Ctrl+Shift+B`快捷执行敏感词检查。

### 字数统计
- `Ctrl+Shift+T`打开任务面板，选择“执行字数统计”，对非以`.`开头名称的目录内所有txt文件进行字数统计。

### 章节大纲
- 在[.noveler/outlines/](.noveler/outlines/)目录中编辑`章节文件名.md`文件，在“NOVELER”视图查看大纲。
