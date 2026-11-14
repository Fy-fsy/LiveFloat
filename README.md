# 浮译 LiveFloat

把**网页/视频/会议里的外语声音**，实时识别并翻译成中文字幕，以**置顶浮窗**的形式显示——即使网页全屏（浏览器 F11 / 视频网站全屏）也能一直浮在最上层。

> 项目仓库：<https://github.com/Fy-fsy/LiveFloat>

> 核心技术思路：直接捕获 Windows **系统播放的声音**（WASAPI 环回，无需虚拟声卡、无需修改播放器），本地 Whisper 语音识别，再走翻译通道，最后渲染到穿透式字幕浮窗。

---

## 功能特性

- 🎧 **系统音频直取**：捕获电脑正在播放的任何声音（浏览器、视频客户端、在线会议、直播）。
- 🧠 **本地语音识别**：faster-whisper，离线、免费、隐私安全（音频不出本机）。
- 🌐 **多翻译通道**：
  - `MyMemory` 免费在线（默认，无需密钥）
  - `DeepSeek / OpenAI 兼容`（质量最佳，需自己的 API Key）
  - `Google 翻译`、`Microsoft Edge 翻译`（实验性）
  - `Argos 离线翻译`：完全离线、无需密钥，首次在软件内下载约 70 MB 模型即可用（英文 ⇄ 中文）
- 🪟 **置顶浮窗**：半透明、可拖拽、可锁定鼠标穿透；全屏视频下依然显示。
- 📜 **历史回溯**：浮窗内可上下滑动查看此前的翻译记录。
- 📝 **字幕记录**：逐句写入 `.md` / `.txt` 文件（按天分文件），支持一键删除历史记录。
- 🌍 **中英文界面**：控制台右上角按钮一键切换，默认简体中文。
- ⌨️ **全局快捷键**：
  - `Ctrl+Alt+F` 显示/隐藏字幕浮窗
  - `Ctrl+Alt+L` 锁定/解锁（鼠标穿透）
  - `Ctrl+Alt+S` 打开控制台
- 📐 字号、不透明度、宽度、历史条数、是否显示原文均可调。

---

## 为什么不用“微软实时字幕”？

Windows 11 的“实时字幕 (Live Captions)”确实好用，但它**没有公开的 API 导出字幕文本**，只能通过 UI 自动化抓取，依赖系统语言包、窗口状态，且不可编程控制，稳定性和可移植性差。本项目改用**直接环回捕获系统音频 + 本地 Whisper**，更通用、更可控，也支持中文/日文/韩文等多种源语言。

---

## 环境要求

- Windows 10 22H2 / Windows 11（64 位）
- Python 3.12（推荐；3.10–3.12 均可）
- 首次运行需联网下载识别模型（约 145 MB，默认走 `hf-mirror.com` 镜像）

---

## 快速开始（源码运行）

1. 双击 **`start.bat`**
   - 首次会自动创建虚拟环境并安装依赖（国内自动使用阿里云 PyPI 镜像）。
2. 打开控制台，点击 **“开始翻译”**
   - 首次会自动下载识别模型，稍等片刻。
3. 播放任意网页外语视频，即可看到底部浮出的双语字幕。

> 若 `start.bat` 未自动装好依赖，可手动执行：
> ```bat
> py -3.12 -m venv .venv
> .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
> .venv\Scripts\python.exe run.py
> ```

---

## 打包为免安装程序

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

产物在 `dist\LiveFloat\LiveFloat.exe`，双击即可运行（仍会在首次运行时下载识别模型）。

---

## 使用建议

1. **播放设备**：在「音频」页选择正在发声的设备（耳机/扬声器）。若网页声音从耳机出来，请选耳机。
2. **源语言**：默认自动检测；若确定是英语，可切到 `Base English` 模型更快更准。
3. **翻译质量**：免费 MyMemory 每日约 5000 词；追求质量请在「翻译」页填入 DeepSeek API Key（模型名 `deepseek-chat`）。
4. **锁定时**：浮窗鼠标穿透，不影响点击网页；用 `Ctrl+Alt+L` 解锁后即可拖拽/点按钮。
5. **停止**：点控制台“停止”，或托盘菜单“停止翻译”。

---

## 目录结构

```
LiveFloat/
├─ app/                 # 主程序
│  ├─ main.py           # 入口
│  ├─ controller.py     # 应用编排
│  ├─ pipeline.py       # 音频→VAD→识别→翻译 管线
│  ├─ audio.py          # WASAPI 环回采集
│  ├─ vad.py            # Silero VAD + 分段器
│  ├─ asr.py            # faster-whisper 识别
│  ├─ translate.py      # 翻译通道
│  ├─ overlay.py        # 置顶字幕浮窗
│  ├─ settings.py       # 控制台
│  └─ ...
├─ assets/              # 图标、Silero VAD 模型
├─ tools/               # 自检脚本
├─ run.py               # 运行入口
├─ start.bat            # 一键启动
├─ build.ps1            # PyInstaller 打包
└─ requirements.txt
```

---

## 数据与日志位置

配置、日志、识别模型、离线翻译模型、字幕记录默认存放在：

- 正常情况：`%LOCALAPPDATA%\LiveFloat\`（含 `config.json`、`logs\`、`models\`、`cache\subtitles\`）
- 若该目录不可写（例如受控/沙箱环境），程序会**自动降级为便携模式**，把数据写到 exe 同目录下的 `LiveFloat-data\`（源码运行则为项目目录下 `.data\`）。

> 这样即使系统目录被权限策略拦截，程序也不会因为写配置失败而崩溃。

## 关于离线翻译（Argos）

采用**单版本内嵌下载**方案（而不是维护“在线版/离线版”两套 exe）：在「翻译」页可勾选“启用离线翻译”，并点击“下载/安装离线模型”即可在软件内下载 Argos 模型（约 70 MB，源为 `argos-net.com`）。这样只维护一份代码，未来改动天然同步，离线只是开关。离线支持英文 ⇄ 中文；其它语言对会回退到在线通道。

## 隐私与免责声明

- 识别在**本地**完成；**在线翻译**会把文本发送到你选择的翻译服务商（MyMemory / DeepSeek 等），请勿输入敏感内容。
- 勾选**离线翻译（Argos）**后，翻译也在本地完成，不联网。

## 致谢

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)
- [PySide6](https://doc.qt.io/qtforpython-6/)
- [soxr](https://github.com/mgeier/python-soundfile)（重采样）
