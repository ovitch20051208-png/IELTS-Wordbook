# 单词 TXT 导入标准与 ChatGPT 提示词

今后请使用 **IELTS-VOCAB/2**，文件编码 **UTF-8**。软件也兼容原来的 v1 文件，但 v2 会把缺失音标或来源的卡片明确列为错误，避免再次导入空音标。

可以直接参考 [通用 TXT 示例模板](IELTS_Wordbook_Import_Template.txt)。软件首次启动时词库为空，请导入自己的词单或手动新增词卡。

## 固定格式

```text
# IELTS-VOCAB/2
=== CARD ===
word: amass
meaning: 积累；聚集（大量）
ipa: /əˈmæs/
example_en: The sisters amassed a valuable art collection.
example_zh: 姐妹俩积累了一批珍贵的艺术收藏品。
source: 剑21T1
priority: A
tags: 阅读,阅读高频1300
note: 英式音标参考 Cambridge UK。

=== CARD ===
word: therapeutic
meaning: 治疗性的；有助于身心健康的
ipa: /ˌθer.əˈpjuː.tɪk/
example_en: Many people find gardening therapeutic.
example_zh: 许多人觉得园艺有助于身心健康。
source: 剑21T1
priority: A
tags: 阅读,健康
note: 英式音标参考 Cambridge UK。
```

| 字段 | 规则 |
| --- | --- |
| word | 必填；英文单词或完整短语，保留空格、连字符、撇号 |
| meaning | 必填；与当前语境及词性对应的中文释义 |
| ipa | 必填；英式 IPA，用 `/.../` 包住；不能写美式音标、中文谐音或占位符 |
| example_en | 英文例句；建议提供；一整句写在同一物理行 |
| example_zh | 例句翻译；可空 |
| source | 必填；只写如 `剑21T1`，多个来源写 `剑21T1 | 剑20T3` |
| priority | A / B 或自定义等级；可空 |
| tags | 多个标签用逗号分隔；听力、阅读等分类可放这里 |
| note | 可空；可写音标参考出处或短语参考读法说明 |

同一词条有多个读音时，例如单复数并列：

```text
word: stimulus / stimuli
ipa: /ˈstɪm.jə.ləs/；/ˈstɪm.jʊ.laɪ/
```

## 来源和重复词如何处理

- `剑21 Test 1 听力 Part 1`、`剑21 Test 1 阅读 Passage 2` 都会自动简写为 **`剑21T1`**，同一套 Test 内不再重复堆叠。
- 假如原有 `amass` 的来源是 `剑21T1`，以后又在剑20 Test3 遇到，只需再导入 `word: amass`、`source: 剑20T3`。系统仍保留一张卡，来源变成 **`剑21T1 | 剑20T3`**。
- 去重忽略大小写、首尾空格和重复空白；不会把不同单词或不同短语粗暴合成一个词。
- 默认补充空白字段，并合并新来源、标签；不会覆盖已有非空人工释义、音标、备注，也不会重置掌握度或历史。另一个导入选项只追加来源和标签，依然不会漏掉新题库来源。
- 新例句不会覆盖已有非空例句。如果同一个词在新题库中有特殊用法，请先放在 note 中供你审核，或在导入后手动整理。

每个字段必须占一行；长例句会在界面自然换行，不要在文件中手动折成多行。字段名使用英文，冒号使用英文 `:`；注释独立一行并以 `#` 开头。文件不用包含 ID、掌握度、测试次数或历史字段，这些由本地软件保存。

软件校验的是格式和必填项；它无法自动证明任意新 IPA 的语言学准确性，因此请让 ChatGPT 核对词典的 UK 标注。不要把模型输出直接称为“已核实”而不检查。

## 可直接复制给 ChatGPT 的提示词

复制以下文字，再附上你要整理的原文、词单以及题库编号：

```text
请把我提供的雅思单词/短语整理成可直接导入 IELTS Wordbook 的 UTF-8 TXT。

我这次的题库来源是：【在这里填写，例如 剑21T1】。

严格要求：
1. 第一行必须是 # IELTS-VOCAB/2。不要输出 Markdown 代码围栏、编号、表格或软件不支持的字段。
2. 每张卡以 === CARD === 开始，包含以下九个字段，每个字段只占一行：
   word / meaning / ipa / example_en / example_zh / source / priority / tags / note。
3. word、meaning、ipa、source 不得为空。其余字段可空，但建议提供语境例句及翻译。
4. ipa 必须使用英式英语 IPA，并写成 /.../。请核对 Cambridge 的 UK 或 Collins 的 British English 等可靠词典；不要混入 US 音标，不要用拼写猜音标，不要用中文谐音。
5. 按本词实际词性、词形和语境选择读音，例如动词 import、动词 advocate、过去分词 heightened / underestimated，以及复数词尾，不要直接照搬其他词性的读音或词干音标。
6. 短语也应有完整的英式参考音标。如果是根据组成词整理的宽式读法，请在 note 中注明“短语参考读法，重音和弱读随语境变化”，不要冒充词典提供的整句标音。能查到整条短语的可靠音标时优先使用。
7. 若某个词的音标确实无法确认，先单独列出需要核对的词并说明，解决后再生成最终 TXT；不要编造，也不要把该词悄悄漏掉或将 ipa 留空。
8. source 只使用“剑21T1”这样的题库简称，不写“听力 Part 1”“阅读 Passage 2”等；同词多个来源用“ | ”连接。
9. tags 可以保留听力、阅读、易听错、阅读高频1300等标签，用英文逗号分隔。不要无依据地把词标成高频或重点。
10. meaning 要符合原文语境；example_en 写自然完整的英文例句，example_zh 为其中文翻译。自行编写的辅助例句不要冒充原文逐字摘录。
11. 同一批内相同英文只输出一次并合并来源和标签。保留短语中的空格、连字符、撇号、斜杠。
12. 多读音用中文分号连接完整的 /.../，例如 /a/；/b/。音标参考网址或补充说明放在 note，不放在题库 source。

固定字段样式：
=== CARD ===
word: amass
meaning: 积累；聚集（大量）
ipa: /əˈmæs/
example_en: The sisters amassed a valuable art collection.
example_zh: 姐妹俩积累了一批珍贵的艺术收藏品。
source: 剑21T1
priority: A
tags: 阅读
note: 英式音标参考 Cambridge UK。

以下是需要整理的原文和词单：
【在这里粘贴材料】
```
