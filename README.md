# DROP · 本地视频下载器

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) Python API 的本地网页下载工具：粘贴链接 → 选清晰度 → 下载合并 MP4。全程本地运行，无广告、无追踪。

## 特性

- 🔗 **粘贴即用**：支持直接粘贴 URL 或 App 分享全文（自动提取链接）
- 📺 **清晰度选择**：1080p / 720p / 480p / 360p，附文件大小预估
- ⚡ **实时进度**：进度条、速度、剩余时间、日志滚动展示，可随时取消
- 🎬 **自动合并**：ffmpeg 自动合并音视频轨为 MP4
- 📂 **目录自选**：点击路径可自选保存位置，并记住你的选择
- 🌐 **1700+ 站点**：YouTube、Bilibili、Twitter/X、TikTok、Instagram 等公开视频

## 快速开始

### 环境要求

- Python 3.9+
- ffmpeg（合并音轨必需）

```bash
# macOS
brew install ffmpeg
```

### 安装与运行

```bash
git clone https://github.com/XuYangSeven/drop-downloader.git
cd drop-downloader
pip install -r requirements.txt
python server.py
```

浏览器打开 **http://127.0.0.1:8777** 即可使用。

macOS 用户也可以直接双击 `启动DROP.command`（首次右键 → 打开）。

## 使用说明

1. 粘贴视频链接（支持 B 站/抖音等 App 的完整分享文案）
2. 点击「解析」查看标题、时长、可选清晰度
3. 选择清晰度后点击「下载」，实时查看进度
4. 完成后点击「打开所在文件夹」取走文件；手机等远程场景点击「保存到本设备」

## 云端部署（手机随时随地用）

GitHub 只托管代码，不运行服务。要在线使用需部署到容器平台，推荐 [Hugging Face Spaces](https://huggingface.co/spaces)（免费）：

1. 注册 Hugging Face 账号 → 创建 Space → 选择 **Docker** 类型、空白模板
2. 上传本仓库全部文件（或在 Space 设置里直接关联本 GitHub 仓库）
3. 在 Space 的 **Settings → Variables and secrets** 添加：

| 变量 | 值 | 说明 |
|---|---|---|
| `DROP_PASSWORD` | 你的密码 | **必设**，公网服务不加密码会被滥用 |
| `DROP_MAX_MB` | `500` | 建议，限制单文件大小 |

4. 等待构建完成，访问 `https://你的用户名-drop.hf.space`——手机浏览器打开，输密码即用，下载完成后点「保存到本设备」直接存进手机

> 云端注意事项：免费额度有限、服务闲置会休眠（首次打开慢）、部分平台（如 YouTube）会屏蔽云服务器 IP。

也支持部署到任何 Docker 主机：

```bash
docker build -t drop .
docker run -d -p 7860:7860 -e DROP_PASSWORD=你的密码 -v drop-data:/data drop
```

## 说明与边界

- 本工具仅适合下载**公开可访问**的视频，用于个人学习/备份
- DRM 加密、需登录、付费/会员内容**不支持**（也不会支持）
- 下载内容请遵守来源站点的服务条款与当地版权法规

## 技术栈

Python · FastAPI · yt-dlp Python API · 原生 HTML/CSS/JS

## License

MIT
