# AI News WeChat

一个免费的每日 AI 新闻微信推送模板。它会从公开 RSS 源抓取 AI 相关新闻，整理成 Markdown 简报，并推送到 PushPlus、WxPusher 或 Server 酱。

## 特点

- 免费运行：可用 GitHub Actions 每天自动执行。
- 免费推送：支持 PushPlus、WxPusher、Server 酱的免费额度。
- 易分发：别人复制仓库后，只需要填自己的 token。
- 无依赖：核心脚本只使用 Python 标准库。

## 本地试运行

```bash
cp .env.example .env
python3 news_push.py
```

默认 `PUSH_PROVIDER=stdout`，会直接在终端打印简报，不会发送微信。

## 推送到 PushPlus

1. 打开 https://www.pushplus.plus/
2. 微信扫码登录并复制你的 token。
3. 修改 `.env`：

```bash
PUSH_PROVIDER=pushplus
PUSHPLUS_TOKEN=你的_token
```

4. 运行：

```bash
python3 news_push.py
```

## 推送到 WxPusher

1. 打开 https://wxpusher.zjiecode.com/
2. 创建应用，获取 `appToken`。
3. 让接收人关注应用，获取用户 `UID`。
4. 修改 `.env`：

```bash
PUSH_PROVIDER=wxpusher
WXPUSHER_APP_TOKEN=你的_appToken
WXPUSHER_UIDS=UID_1,UID_2
```

## 推送到 Server 酱

1. 打开 https://sct.ftqq.com/
2. 登录并获取 `SendKey`。
3. 修改 `.env`：

```bash
PUSH_PROVIDER=serverchan
SERVERCHAN_SENDKEY=你的_SendKey
```

## 用 GitHub Actions 免费定时运行

1. 把本项目上传到 GitHub。
2. 进入仓库 `Settings` -> `Secrets and variables` -> `Actions`。
3. 新增 secrets：

```text
PUSH_PROVIDER=pushplus
PUSHPLUS_TOKEN=你的_token
```

如果使用 WxPusher 或 Server 酱，就换成对应变量。

4. 打开 `Actions` 页面，启用 workflow。

默认每天北京时间 09:00 执行。要改时间，编辑 `.github/workflows/daily.yml` 里的 cron。GitHub Actions 的 cron 使用 UTC 时间。

## 自定义新闻源

编辑 `config/feeds.txt`，每行一个 RSS 地址。例如：

```text
https://openai.com/news/rss.xml
https://www.anthropic.com/news/rss.xml
```

建议优先使用官方博客、权威媒体、研究机构和产品发布源。

如果添加 36氪这类综合新闻源，脚本会根据 `NEWS_KEYWORDS` 自动过滤 AI 相关内容。

默认只保留最近 7 天的内容。可以通过 `.env` 或 GitHub Secrets 设置：

```bash
NEWS_RECENT_DAYS=3
NEWS_LIMIT=10
```

## 打包发给别人

把整个 `ai-news-wechat` 文件夹压缩成 zip 即可。接收者解压后按 README 配置自己的 token。

注意：不要把你的 `.env` 一起发出去，里面可能有私密 token。

## 进阶方向

- 接入 OpenAI、Claude、DeepSeek 或本地 Ollama 做更像人的中文摘要。
- 增加 AIBase、36氪等网页源的专用抓取器。
- 做成桌面 App，让用户填 token 和推送时间。
- 做成一键部署模板，降低非技术用户门槛。
