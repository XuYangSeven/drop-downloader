#!/usr/bin/env python3
"""DROP — 本地视频下载网页工具, 基于 yt-dlp Python API.

用法: python server.py   然后访问 http://127.0.0.1:8777
"""

import os
import re
import subprocess
import threading
import uuid
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path(os.environ.get('DROPLY_DIR') or (BASE_DIR / 'downloads')).expanduser()
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = BASE_DIR / '.saved-dir'  # 记住上次选择的保存目录


def load_saved_dir():
    global DOWNLOAD_DIR
    try:
        p = Path(CONFIG_FILE.read_text().strip()).expanduser()
        if p.is_dir():
            DOWNLOAD_DIR = p
            return
    except Exception:  # noqa: BLE001
        pass
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


load_saved_dir()

app = FastAPI(title='DROP')

# ---------------------------------------------------------------- 任务存储

TASKS: dict[str, dict] = {}
TASK_LOCK = threading.Lock()


def new_task() -> dict:
    task_id = uuid.uuid4().hex[:12]
    task = {
        'id': task_id,
        'status': 'pending',  # pending | downloading | merging | finished | error | canceled
        'progress': 0.0,
        'speed': '',
        'eta': '',
        'total': 0,
        'downloaded': 0,
        'filename': '',
        'error': '',
        'log': deque(maxlen=30),
        'cancel': threading.Event(),
    }
    with TASK_LOCK:
        TASKS[task_id] = task
    return task


def push_log(task, line):
    task['log'].append(line)


# ---------------------------------------------------------------- 解析

class ParseReq(BaseModel):
    url: str


HINT_MAP = [
    ('unsupported url', '链接不受支持，请检查是否完整'),
    ('video unavailable', '视频不可用，可能已删除或为私密视频'),
    ('login', '该内容需要登录才能访问'),
    ('private', '该视频为私有视频'),
    ('geo', '该内容有地区限制'),
    ('http error 429', '请求过于频繁，请稍后重试'),
]


def friendly_error(exc) -> str:
    msg = str(exc)
    for key, hint in HINT_MAP:
        if key in msg.lower():
            return f'{hint}（{msg.splitlines()[0][:200]}）'
    return msg.splitlines()[0][:300] if msg else '未知错误'


URL_RE = re.compile(r'https?://[^\s\'"<>()【】\u4e00-\u9fff]+', re.IGNORECASE)


def extract_url(text: str) -> str:
    """从粘贴文本中提取第一个 URL（兼容 B 站等 App 分享文案）"""
    if not text:
        return ''
    m = URL_RE.search(text)
    return m.group(0).rstrip('.,;:!?，。；：！？') if m else text.strip()


@app.post('/api/parse')
def parse(req: ParseReq):
    url = extract_url(req.url)
    if not url:
        raise HTTPException(400, '链接为空')

    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            raw = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        return JSONResponse({'ok': False, 'error': friendly_error(e)}, 400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({'ok': False, 'error': friendly_error(e)}, 500)

    if raw.get('_type') == 'playlist':
        entries = [e for e in raw.get('entries') or [] if e]
        if not entries:
            return JSONResponse({'ok': False, 'error': '播放列表为空'}, 400)
        raw = entries[0]

    formats = raw.get('formats') or []
    heights = sorted({
        f.get('height') for f in formats
        if f.get('height') and f.get('vcodec') != 'none'
    }, reverse=True)

    def size_for_height(h):
        cands = [f for f in formats if f.get('height') == h]
        return max((f.get('filesize') or f.get('filesize_approx') or 0) for f in cands) if cands else 0

    def fmt_size(n):
        if not n:
            return ''
        mb = n / 1024 / 1024
        return f'{mb:.0f} MB' if mb >= 1 else f'{n/1024:.0f} KB'

    info = {
        'ok': True,
        'title': raw.get('title') or '',
        'uploader': raw.get('uploader') or raw.get('channel') or '',
        'duration': raw.get('duration') or 0,
        'thumbnail': raw.get('thumbnail') or '',
        'extractor': raw.get('extractor_key') or '',
        'qualities': [
            {'height': h, 'label': f'{h}p', 'size': fmt_size(size_for_height(h)),
             'recommended': h == max(heights) if heights else False}
            for h in heights
        ],
    }
    return info


# ---------------------------------------------------------------- 下载

class DownloadReq(BaseModel):
    url: str
    height: int = 1080


def run_download(task_id: str, url: str, height: int):
    task = TASKS[task_id]

    def progress_hook(d):
        if task['cancel'].is_set():
            raise yt_dlp.utils.DownloadCancelled()
        if d.get('status') == 'downloading':
            task['status'] = 'downloading'
            task['downloaded'] = d.get('downloaded_bytes') or 0
            task['total'] = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            task['progress'] = d.get('_percent_str', '').strip() if d.get('_percent_str') else (
                task['downloaded'] / task['total'] * 100 if task['total'] else 0)
            task['speed'] = d.get('_speed_str', '').strip()
            task['eta'] = d.get('_eta_str', '').strip()
        elif d.get('status') == 'finished':
            task['progress'] = 100.0
            push_log(task, '[download] 下载完成，正在合并音轨 ...')
        elif d.get('status') == 'error':
            push_log(task, f'[error] {d.get("filename", "")}')

    def postprocessor_hook(d):
        if d.get('status') == 'started':
            task['status'] = 'merging'
            push_log(task, '[merge] 正在合并视频与音轨 ...')
        elif d.get('status') == 'finished':
            task['filename'] = os.path.basename(d.get('info_dict', {}).get('filepath') or task['filename'])

    opts = {
        'outtmpl': str(DOWNLOAD_DIR / '%(title).80s [%(id)s].%(ext)s'),
        'format': f'bv*[height<={height}]+ba/b[height<={height}]',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
        'postprocessor_hooks': [postprocessor_hook],
        'concurrent_fragment_downloads': 4,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            raw = ydl.extract_info(url, download=True)
        if raw:
            name = ydl.prepare_filename(raw)
            task['filename'] = os.path.basename(name)
            # merge 后实际文件为 mp4
            base = re.sub(r'\.\w+$', '.mp4', task['filename'])
            if (DOWNLOAD_DIR / base).exists():
                task['filename'] = base
        task['status'] = 'finished'
        task['progress'] = 100.0
        push_log(task, f'[done] 已保存 {task["filename"]}')
    except yt_dlp.utils.DownloadCancelled:
        task['status'] = 'canceled'
        push_log(task, '[cancel] 已取消下载')
    except Exception as e:  # noqa: BLE001
        task['status'] = 'error'
        task['error'] = friendly_error(e)
        push_log(task, f'[error] {task["error"]}')


@app.post('/api/download')
def download(req: DownloadReq):
    url = extract_url(req.url)
    if not url:
        raise HTTPException(400, '链接为空')
    task = new_task()
    push_log(task, f'[start] {req.height}p · {url}')
    threading.Thread(target=run_download, args=(task['id'], url, req.height), daemon=True).start()
    return {'task_id': task['id']}


@app.get('/api/tasks/{task_id}')
def task_status(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, '任务不存在')
    return {
        'id': task['id'],
        'status': task['status'],
        'progress': round(float(task['progress'] or 0), 1),
        'speed': task['speed'],
        'eta': task['eta'],
        'total': task['total'],
        'downloaded': task['downloaded'],
        'filename': task['filename'],
        'error': task['error'],
        'log': list(task['log']),
    }


@app.post('/api/tasks/{task_id}/cancel')
def cancel_task(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, '任务不存在')
    task['cancel'].set()
    return {'ok': True}


@app.get('/api/download-dir')
def download_dir():
    return {'dir': str(DOWNLOAD_DIR)}


@app.post('/api/pick-dir')
def pick_dir():
    """弹出 macOS 原生目录选择框, 选择后持久化并立即生效."""
    global DOWNLOAD_DIR
    script = (
        'set chosen to choose folder with prompt "选择视频保存位置"\n'
        'return POSIX path of chosen'
    )
    try:
        out = subprocess.run(
            ['osascript', '-e', script], capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': '选择超时'}
    if out.returncode != 0:
        return {'ok': False, 'error': '已取消'}
    p = Path(out.stdout.strip()).expanduser()
    if not p.is_dir():
        return {'ok': False, 'error': '目录无效'}
    DOWNLOAD_DIR = p
    try:
        CONFIG_FILE.write_text(str(p))
    except Exception:  # noqa: BLE001
        pass
    return {'ok': True, 'dir': str(p)}


@app.get('/api/open-folder')
def open_folder():
    subprocess.Popen(['open', str(DOWNLOAD_DIR)])
    return {'ok': True}


@app.get('/api/thumb')
def thumb(url: str):
    """代理缩略图, 避免混合内容/防盗链问题."""
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = r.read()
    return Response(content=data, media_type='image/jpeg', headers={'Cache-Control': 'public, max-age=3600'})


app.mount('/', StaticFiles(directory=str(BASE_DIR / 'static'), html=True), name='static')


if __name__ == '__main__':
    import uvicorn
    print(f'Download dir: {DOWNLOAD_DIR}')
    print('Open http://127.0.0.1:8777')
    uvicorn.run(app, host='127.0.0.1', port=8777, log_level='warning')
