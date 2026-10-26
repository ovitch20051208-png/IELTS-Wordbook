# IELTS Wordbook

Windows 本地雅思背单词软件。Python 3.11+、PySide6 Qt Widgets、SQLite；简体中文界面，无账号、无服务器、无付费 API。安装好依赖及所需系统语音后，学习功能完全离线。

## 最快开始

源码用户请先安装 64 位 Python 3.11+，再双击 **`run_windows.bat`**；脚本会自动创建 `.venv` 并安装依赖，首次安装需要联网。

也可从 [GitHub Releases](https://github.com/ovitch20051208-png/github_wordcard/releases/latest) 下载 Windows 压缩包，完整解压后双击 **`IELTSWordbook.exe`**，无需安装 Python。请保留它旁边的 `_internal` 文件夹。

第一次启动时，**词库、学习记录和测试历史均为空**。可在“单词库”新增词卡，或在“导入 / 导出与设置”中导入自己的 TXT。首页 **“导入示例词卡”** 提供 8 张通用格式示例，经预览并确认后才写入；软件不会自动导入任何词库。

**开源首版 v1.0.0**：正反面均可自评，音标在正反面显示。来源自动简写为 `剑21T1`；同词跨题库重复导入只追加来源，不新增卡片。发布包不包含个人词库、数据库、备份或学习记录。

今后生成单词文件，请使用 [标准格式与可复制的 ChatGPT 提示词](导入格式与ChatGPT提示词.md) 和 [TXT 模板](IELTS_Wordbook_Import_Template.txt)。

正式数据自动保存在：

```text
%LOCALAPPDATA%\IELTSWordbook\wordbook.db
```

升级源码或重新打包不会移动或清空这个数据库。测试均使用项目内隔离数据库，没有把模拟测试成绩写入正式词库。

## 从零安装（Windows 10 / 11）

1. 安装 [64 位 Python 3.11 或更新版本](https://www.python.org/downloads/windows/)，勾选 **Add python.exe to PATH**。本项目实际验证版本为 Python 3.12.10。
2. 下载并完整解压源码（或使用 Git 克隆），将整个项目放在一个可写目录，保留 `IELTS_Wordbook_Import_Template.txt` 和 `wordbook/data/`。
3. 双击 `install_windows.bat`，等待依赖安装完毕。首次安装需要联网；依赖装好后不再需要联网。
4. 双击 `run_windows.bat`。如果依赖缺失，启动脚本会自动调用安装脚本。

也可在项目目录的 PowerShell 手动执行，无需激活虚拟环境：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

依赖锁定为本次验证过的 PySide6 6.11.2、pywin32 312。运行不需要管理员权限。如安装报错，请检查 Python 是否为 64 位、网络连接及终端错误输出。

## 日常使用

- **首页**：总词数、未测试、已掌握、有一点印象、完全记不得与最近测试时间。点击数字进入相应分类。
- **单词库**：搜索英文或中文；按状态、来源、优先级、标签组合筛选。双击词卡进入详情，修改内容及掌握度后点击“保存”。删除需要确认，历史保留原英文。
- **指定数量测试**：选择状态、来源、标签，数量可选 5 / 10 / 20 / 30 / 50 / 100 或自定义。候选不足时提示最大可用数量，不会暗中缩减；每轮不重复。
- **全库随机测试**：仅使用数量设置，忽略状态、来源、标签，从整个词库抽题；已掌握的词同样可能出现。
- **闪卡**：正面展示英文、英式音标和简称来源。点卡面、主按钮或 `Space` 查看答案；正反面均可点击或按 `1` 已掌握、`2` 有一点印象、`3` 完全记不得，立即保存并进入下一张，不再出现正面彩色按钮点击无反应的问题。暂停时不可判定；误点可撤销。
- **跳过 / 暂停 / 撤销 / 结束**：跳过及仅翻面均不更改状态。撤销本轮最后一次判定，会恢复原状态、累计次数及最近复习时间，并在历史中保留“已撤销”的记录。最后一张作答完毕后，也可从结果页撤销；主动结束本轮后不可再撤销。
- **复习历史**：可按英文、结果、测试会话筛选，包含手动状态调整和撤销标记。下方显示会话列表。删除卡片不删除历史；同名词重新添加后获得新 ID。
- 测试进行中，先结束本轮，再编辑、删除、导入或恢复词库，避免测试快照与数据修改互相影响。关闭软件时会提示结束未完成的本轮；已作答的结果始终保留。退出后不自动恢复尚未作答的抽题队列。

## 本地英语朗读

- 闪卡正面英文旁的 **🔊 单词** 朗读单词或完整短语，不会翻面。反面英文例句旁的 **🔊 例句** 只朗读完整英文例句。详情编辑页也有两处独立试听。
- “导入 / 导出与设置”列出 **Windows SAPI5 可访问的本机发音人及语言**，优先选择 `en-GB`，否则选择其他可用英语，明确提示实际口音；允许自行切换并保存选择。
- 提供 `1.0×` 标准和约 `0.8×` 慢速，重复播放 1–5 次。SAPI 各发音人的速率实现不同，慢速是 SAPI Rate=-2 的近似档位，并非精确时间拉伸。
- 新一次朗读会清除旧朗读队列；翻卡、暂停、切页和退出时停止播放。COM 引擎只在专用工作线程中使用，播放不会阻塞界面，退出时释放。
- `ipa` 为空时仍可朗读，但音标继续显示 **“音标待补充”**。软件不会根据拼写生成 IPA，也不会把 TTS 视为已核实的词典发音。
- 无可用英语语音时，软件提示安装方法，其余学习功能照常工作。安装语音可能需要联网，但日常播放不联网。

添加英式英语语音：**Windows 设置 → 时间和语言 → 语言和区域 → 添加 English (United Kingdom) → 语言选项 → 安装“语音”**，安装完成后重启本软件。不同 Windows 版本菜单名称略有差异。部分仅供讲述人使用的自然语音不支持 SAPI5，不会出现在本程序列表中；必要时在经典控制面板的“文本到语音”中确认可用发音人。

本次验收的电脑只有 Microsoft Zira Desktop（`en-US`）和 Microsoft Huihui Desktop（`zh-CN`），**尚未安装 en-GB**；已完成 Zira 的真实本地朗读调用和界面口音标示验证。不会自动下载语音或修改系统注册表。

## TXT 标准、预览和去重

推荐使用 `IELTS-VOCAB/2`，同时兼容旧 `IELTS-VOCAB/1`。编码为 UTF-8 或带 BOM 的 UTF-8；允许空行和以 `#` 开头的注释：

```text
# IELTS-VOCAB/2
=== CARD ===
word: coincide with
meaning: 与……同时发生
ipa: /ˌkəʊ.ɪnˈsaɪd wɪð/
example_en: Their visit coincided with an exhibition.
example_zh:
source: 剑21T1
priority: A
tags: 阅读,阅读高频1300
note: 短语参考读法，重音和弱读随语境变化。
```

v2 的 `word`、`meaning`、`ipa`、`source` 必填；多个读音可写 `/.../；/.../`。旧 v1 仍只要求 `word`、`meaning`，允许原始空音标。字段顺序不限。每个字段的内容写在同一物理行中，界面会自动换行。英文冒号只在第一次出现时分割，因此例句里的冒号、中文标点、短语空格、连字符、撇号、斜杠均可保留。标签使用逗号分隔；合并的多个来源用 ` | ` 分隔。

预览显示解析张数、有效张数、预计新增 / 更新 / 重复与全部错误原因和行号。未知字段、重复字段、缺失必填项、缺少冒号会明确报错；错误卡片不写入，正确卡片仍可确认导入。错误项数包括卡片外格式错误，因此不一定等于失败卡片数。

去重键是英文 `strip + casefold + 连续空白合并`。默认只补齐已有卡片的空白字段，并合并来源及标签；**不覆盖非空人工修改，不改变状态、ID、累计次数及历史**。也可选择“仅追加来源和标签”。同一文件内重复词条同样会去重。例如同词先在剑21 Test1、再在剑20 Test3 出现，最终仍是一张卡，来源为 `剑21T1 | 剑20T3`。导入在后台线程运行，并用单个 SQLite 事务提交；发生写入错误时整批回滚。

`priority: A`、`五星阅读词`、`阅读高频1300` 在详情 / 闪卡背面标记为重点，且可通过优先级或标签筛选。没有 100 张限制；自动化测试覆盖 5000 张导入与不重复抽样。

## 导出、备份与恢复

- **导出全部词卡 TXT**：导出全部内容为同一种标准格式，便于继续补充或往返导入；不包含学习状态及历史。全部卡片都有音标、来源时导出 v2；包含旧版缺失项时导出 v1 以保证可往返导入。
- **完整备份 SQLite**：包含所有词卡、稳定 ID、当前状态、历史、测试会话及语音设置。使用 SQLite 在线备份接口，不直接复制可能仍有 WAL 的 `.db` 文件。
- **恢复完整备份**：需确认；先校验版本、结构、完整性及关联，再自动保存 `before_restore_*.db` 于数据目录，随后替换现有数据。可从自动备份再次恢复。
- 一次只允许一个使用相同数据目录的程序实例。关闭软件后迁移文件时，建议优先使用上述完整备份；不要只复制正在使用的 `.db` 而漏掉 WAL。

## 测试与实际验收

双击 `test_windows.bat`，或执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

自动化测试使用临时数据库和自动生成的测试词卡，覆盖首次启动空词库、通用示例、v2 必填项、跨题库来源追加、内容升级不改学习数据、UTF-8/BOM/中文/音标、重复导入、错误定位、事务回滚、5000 条词库、三档状态转换、全库随机、无重复、正反面真实鼠标点击三个掌握度按钮、跳过、撤销、重启保存、完整备份恢复、两个喇叭的独立文本、语音降级及后台导入完整流程。

可选的 Windows 原生窗口 / 系统朗读验收命令（会短暂打开窗口并播放声音，使用项目内独立数据库）：

```powershell
.\.venv\Scripts\python.exe tools\windows_smoke.py --audio
```

其报告和 Windows 原生界面截图写入 `.test-artifacts/`。普通测试使用 Qt offscreen，Windows 下该后端可能不加载系统字体，其截图不代表真实窗口；原生窗口截图以 `windows_*.png` 为准。

## 打包为 exe

在 Windows 上双击 `build_windows.bat`：安装打包依赖 → 跑完整测试 → PyInstaller 打包。或手动执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean IELTSWordbook.spec
```

产物为 `dist\IELTSWordbook\IELTSWordbook.exe`。分发时复制 **整个 `dist\IELTSWordbook` 文件夹**，不能只拿走 exe。此方式不要求目标电脑安装 Python；目标系统仍需提供可用的 Windows 语音。数据仍位于目标用户的 `%LOCALAPPDATA%\IELTSWordbook`。

## 项目结构与维护

```text
main.py                     应用入口、实例锁、日志和异常提示
wordbook/models/            词卡模型与规范化规则
wordbook/storage/           SQLite、历史、事务导入、备份恢复
wordbook/importer/          TXT 解析与往返导出
wordbook/services/          抽题复习会话、Windows SAPI5 异步朗读
wordbook/ui/                中文桌面页面、编辑详情及导入预览
tests/                      自动化测试
tools/windows_smoke.py      原生界面与系统语音验收
```

异常日志为数据目录中的 `wordbook.log`。开发隔离时可设置 `IELTS_WORDBOOK_DATA_DIR` 指向测试目录，正常使用无需设置。

首版没有复杂间隔重复算法、联网 IPA 查询和未完成题队列的跨重启续做；这些不影响已实现的核心流程。尚未在其他 Windows 10/11 电脑及不同 SAPI 发音人上做兼容性实测。

实现参考：[Qt 模型与线程规则](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractItemModel.html)、[Microsoft SAPI 异步、清队列及纯文本标志](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ee125223(v=vs.85))。

## 开源许可

项目代码和通用示例采用 [MIT 许可](LICENSE)。第三方依赖沿用各自许可证，见 [第三方组件说明](THIRD_PARTY_NOTICES.md)。
