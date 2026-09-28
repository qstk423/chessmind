# ChessCouncil Mac 比赛版

这是在 Mac 独立窗口中运行的比赛演示版。解压 `ChessCouncil-Mac.zip` 后，双击
`ChessCouncil.app` 即可打开；不用手动打开网页或启动服务器。请保持整个 `.app`
完整，不要只复制其中的可执行文件。

## 模型配置

基础棋盘、引擎分析和本地功能不需要模型 Key。若要现场展示 GLM / 千问调用，
将 `ChessCouncil.env.example` 复制为 `ChessCouncil.env`，放在 `.app` 同一个文件夹，
仅在自己的电脑上填写 Key。也可把私有配置放在
`~/Library/Application Support/ChessCouncil/config.env`。配置后重新打开应用。

如模型服务提供完整的 `/chat/completions` 地址，`LLM_BASE_URL` 应填写其上一级
基础地址（通常以 `/v1` 结尾），不要把 `/chat/completions` 也写进去。
模型调用仍需要现场网络。请勿将填写过 Key 的配置文件放进压缩包或上传 GitHub。

## 数据与排障

本地对局数据库、`logs/llm_calls.jsonl` 和 `desktop.log` 位于
`~/Library/Application Support/ChessCouncil`。如遇启动失败，请查看 `desktop.log`。
应用关闭后，它启动的本机服务也会退出。

桌面版只监听本机回环地址。导航包含对弈、学习、工具，联机功能已移除。

本包自带 Stockfish 19 和与本机网页项目相同的 Pikafish 中国象棋引擎及 NNUE 参数。
两者的许可证及源代码包保留在 `.app` 内的 `third_party` 目录；中国象棋
不再因窗口封装而降级为内建搜索。
此包是本机演示版，未做 Apple Developer 公证，不建议作为公开分发安装包。

## 重新构建

在 Mac 的项目目录中安装依赖后运行 `bash scripts/build_macos.sh`。脚本会执行
自动测试、校验官方 Stockfish 下载包、构建应用、运行无窗口自检并生成压缩包。
