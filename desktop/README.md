# ChessCouncil Windows 比赛版

此版本将现有国际象棋和中国象棋界面显示在独立桌面窗口中。双击
`ChessCouncil.exe` 会启动本机服务并打开窗口，不需要手动打开浏览器。
窗口关闭时，本机服务也会退出。

## 使用

1. 解压整个 `ChessCouncil-Windows.zip`，不要只复制其中的 exe。
2. 如需在比赛中演示 GLM / 千问模型，将 `ChessCouncil.env.example` 复制为
   `ChessCouncil.env`，放在 exe 旁边，并在**自己的电脑上**填写模型 Key。
   也可把私有配置放在 `%LOCALAPPDATA%\ChessCouncil\config.env`。
3. 双击 `ChessCouncil.exe`。它会自动选一个空闲的本机端口，不会弹出浏览器。

没有配置模型 Key 时，基础对弈和页面仍能打开，但模型分析不可用。
桌面窗口不等于离线模型；比赛现场演示模型调用仍需网络畅通。
**不要把填写过 Key 的配置文件上传 GitHub、放进压缩包或发给评委。**

运行数据位于 `%LOCALAPPDATA%\ChessCouncil`：

- `chesscouncil.db`：对局历史
- `logs\llm_calls.jsonl`：模型调用日志
- `desktop.log`：启动故障记录

本包自带 Stockfish 19；其 GPLv3 许可证与官方原始发行包（含源代码）位于
`_internal\third_party\stockfish`。中国象棋默认使用内建搜索，
未额外打包 Pikafish。Windows 需要 WebView2 运行时；若电脑缺少它，
请先从微软官方安装。当前包没有代码签名，适合团队自己的比赛电脑演示，
不是面向公众分发的正式安装程序。

## 开发者构建

在 Windows 10/11 x64 环境中：

```powershell
python -m pip install -r requirements-desktop.txt
./scripts/build_windows.ps1
```

脚本会运行测试、下载并校验官方 Stockfish 19、构建 exe、
执行无窗口自检，再生成 `dist\ChessCouncil-Windows.zip`。
GitHub Actions 的 “Windows desktop package” 工作流使用同一脚本，
成功后可从该次运行的 Artifacts 下载压缩包。
