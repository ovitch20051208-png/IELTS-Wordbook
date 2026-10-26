# 第三方组件说明

IELTS Wordbook 的项目代码采用 MIT 许可。Python、Qt、PySide6 等第三方组件保留各自的版权与许可，项目的 MIT 许可不替代这些许可。

Windows 发布包使用以下组件：

| 组件 | 用途 | 许可及源码 |
| --- | --- | --- |
| Python | 运行时 | PSF License；https://www.python.org/downloads/source/ |
| PySide6、Shiboken6 | Python / Qt 绑定 | LGPL-3.0 等；https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Qt 6 | 窗口及界面 | LGPL-3.0 / GPL-3.0 及组件许可；https://code.qt.io/cgit/qt/ |
| pywin32 | Windows SAPI5 本地语音 | Python Software Foundation 风格许可；https://github.com/mhammond/pywin32 |
| PyInstaller | 打包工具及引导程序 | GPL-2.0-or-later，包含分发引导程序的例外；https://github.com/pyinstaller/pyinstaller |

随包附带的许可证文本位于 `_internal/third_party_licenses/`，源码中的副本位于 `third_party_licenses/`。Qt / PySide6 使用独立的动态链接库，位于 `_internal/`；可从对应项目获取相应版本的源码、许可证及重新构建说明。

Windows 系统语音由用户的操作系统提供，发布包不包含语音模型。通用示例的例句为本项目编写；发布包不包含个人词库或原有 149 词资料。
