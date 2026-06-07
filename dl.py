import sys
import subprocess
import os
import re
import threading
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.ttk as ttk

PCT_PATTERN      = re.compile(r'\[download\]\s+([\d.]+)%')
PLAYLIST_PATTERN = re.compile(r'\[download\] Downloading (?:video|item) (\d+) of (\d+)')

TYPE_LABELS = {
    'video_best': '影片 - 最高畫質',
    'video_h264': '影片 - 相容模式',
    'mp3':        '音訊 - MP3',
    'm4a':        '音訊 - M4A',
}


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def run_download(url, output_path, download_type, q, proc_ref, stop_event):
    try:
        if stop_event.is_set():
            q.put(('done_stop',))
            return
        os.makedirs(output_path, exist_ok=True)

        yt_dlp_path = resource_path("yt-dlp.exe")
        ffmpeg_path = resource_path("")

        command = [
            yt_dlp_path,
            '--ffmpeg-location', ffmpeg_path,
            '--newline',
            '-o', '%(upload_date)s - [%(uploader)s][%(id)s] %(title)s.%(ext)s',
            url
        ]

        is_video = download_type in ('video_h264', 'video_best')

        if download_type == 'video_h264':
            command.extend(['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4', '--merge-output-format', 'mp4'])
        elif download_type == 'video_best':
            command.extend(['-f', 'bestvideo+bestaudio/best', '--merge-output-format', 'mp4'])
        elif download_type == 'mp3':
            command.extend(['--extract-audio', '--audio-format', 'mp3', '--audio-quality', '0'])
        elif download_type == 'm4a':
            command.extend(['--extract-audio', '--audio-format', 'm4a'])

        phase          = None
        dest_count     = 0
        is_playlist    = False
        current_video  = 0
        total_videos   = 0
        title_sent     = False
        stderr_lines   = []
        error_segments = []  # list of (video_index, error_line)

        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            cwd=output_path
        )
        proc_ref[0] = proc
        if stop_event.is_set():
            proc.terminate()
            proc.wait()
            q.put(('done_stop',))
            return

        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            stderr_lines.append(line)

            # Playlist 進度行：Downloading video X of Y
            pm = PLAYLIST_PATTERN.match(line)
            if pm:
                is_playlist   = True
                current_video = int(pm.group(1))
                total_videos  = int(pm.group(2))
                dest_count    = 0
                phase         = None
                title_sent    = False
                q.put(('playlist', current_video, total_videos))
                continue

            # 錯誤行
            if line.startswith('ERROR:'):
                if is_playlist:
                    error_segments.append((current_video, line))
                continue

            # Destination 行：判斷階段 + 解析標題
            if '[download] Destination:' in line:
                dest_count += 1
                filename = line.split('[download] Destination:', 1)[1].strip()

                # 從檔名解析標題（格式：YYYYMMDD - [uploader][id] title.ext）
                if not title_sent or is_playlist:
                    parts = filename.rsplit('] ', 1)
                    if len(parts) == 2:
                        raw_title = parts[1]
                        # 移除 .f137.mp4 或 .mp4 之類的副檔名
                        title = re.sub(r'\.(f\d+\.)?\w+$', '', raw_title)
                        q.put(('title', title))
                        if not is_playlist:
                            title_sent = True

                if is_video:
                    if dest_count == 1:
                        phase = 'video'
                        q.put(('phase', 'video'))
                    elif dest_count == 2:
                        q.put(('progress', 'video', 100.0))
                        phase = 'audio'
                        q.put(('phase', 'audio'))
                else:
                    if dest_count == 1:
                        phase = 'audio'
                        q.put(('phase', 'audio'))
                continue

            # 合併階段
            if '[Merger]' in line:
                q.put(('progress', 'audio', 100.0))
                phase = 'merge'
                q.put(('phase', 'merge'))
                continue

            # 轉換階段
            if '[ExtractAudio]' in line:
                q.put(('progress', 'audio', 100.0))
                phase = 'convert'
                q.put(('phase', 'convert'))
                continue

            # 下載百分比
            mm = PCT_PATTERN.search(line)
            if mm and phase in ('video', 'audio'):
                q.put(('progress', phase, float(mm.group(1))))

        proc.wait()

        if stop_event.is_set():
            q.put(('done_stop',))
            return

        if error_segments:
            succeeded  = total_videos - len(error_segments)
            error_text = '\n\n'.join(f'[影片 {idx}]\n{err}' for idx, err in error_segments)
            q.put(('done_partial', succeeded, total_videos, error_text))
        elif proc.returncode != 0:
            q.put(('done', False, '\n'.join(stderr_lines)))
        else:
            q.put(('done', True, ''))

    except Exception as e:
        q.put(('done', False, str(e)))


class DownloadItem:
    def __init__(self, parent, url, download_type, output_path):
        self._url           = url
        self._output_path   = output_path
        self._download_type = download_type
        self._q             = queue.Queue()
        self._error_text    = ''
        self._pl_current    = 0
        self._pl_total      = 0
        self._current_phase = None
        self._current_pct   = 0.0
        self._destroyed     = False
        self._proc_ref      = [None]
        self._stop_event    = threading.Event()

        self._build_ui(parent)
        self._start()

    def _build_ui(self, parent):
        self.frame = tk.Frame(parent, relief=tk.RIDGE, borderwidth=1)
        self.frame.pack(fill=tk.X, padx=5, pady=2)

        # 第一列：類型標籤 + 標題
        row0 = tk.Frame(self.frame)
        row0.grid(row=0, column=0, sticky='ew', padx=5, pady=(5, 0))

        tk.Label(row0,
                 text=f'[{TYPE_LABELS.get(self._download_type, "")}]',
                 fg='white', bg='#555555',
                 font=('Arial', 8), padx=4, pady=1).pack(side=tk.LEFT)

        self._title_label = tk.Label(row0, text=self._url,
                                     anchor='w', font=('Arial', 9, 'bold'))
        self._title_label.pack(side=tk.LEFT, padx=(5, 0))

        # 第二列：URL
        tk.Label(self.frame, text=self._url,
                 fg='gray', font=('Arial', 8),
                 anchor='w').grid(row=1, column=0, sticky='ew', padx=5, pady=(0, 5))

        # 右側進度區（rowspan=2）
        prog = tk.Frame(self.frame)
        prog.grid(row=0, column=1, rowspan=2, sticky='ns', padx=(0, 8), pady=5)

        self._bar = ttk.Progressbar(prog, length=200, mode='determinate', maximum=100)
        self._bar.pack()

        self._status_label = tk.Label(prog, text='準備中', font=('Arial', 8), width=22)
        self._status_label.pack(pady=(2, 0))

        self._stop_btn = tk.Button(prog, text='中止', font=('Arial', 8),
                                   fg='#c0392b', command=self._stop_download)
        self._stop_btn.pack(pady=(4, 0))

        self._error_btn = tk.Button(prog, text='查看錯誤', font=('Arial', 8),
                                    fg='red', command=self._show_error)

        tk.Button(self.frame, text='✕', font=('Arial', 10), fg='#999999',
                  relief=tk.FLAT, cursor='hand2',
                  command=self._delete).grid(row=0, column=2, sticky='ne', padx=(0, 4), pady=(3, 0))

        self.frame.columnconfigure(0, weight=1)

    def _start(self):
        threading.Thread(
            target=run_download,
            args=(self._url, self._output_path, self._download_type,
                  self._q, self._proc_ref, self._stop_event),
            daemon=True
        ).start()
        self.frame.after(100, self._poll)

    def _poll(self):
        if self._destroyed:
            return
        try:
            while True:
                msg  = self._q.get_nowait()
                kind = msg[0]

                if kind == 'title':
                    self._title_label.config(text=msg[1])

                elif kind == 'playlist':
                    self._pl_current    = msg[1]
                    self._pl_total      = msg[2]
                    self._current_phase = None
                    self._current_pct   = 0.0
                    self._bar.stop()
                    self._bar.config(mode='determinate')
                    self._bar['value'] = 0
                    self._update_status()

                elif kind == 'phase':
                    self._current_phase = msg[1]
                    self._current_pct   = 0.0
                    if msg[1] in ('merge', 'convert'):
                        self._bar.config(mode='indeterminate')
                        self._bar.start(10)
                    else:
                        self._bar.stop()
                        self._bar.config(mode='determinate')
                        self._bar['value'] = 0
                    self._update_status()

                elif kind == 'progress':
                    self._current_pct  = msg[2]
                    self._bar['value'] = msg[2]
                    self._update_status()

                elif kind == 'done':
                    self._stop_btn.pack_forget()
                    self._bar.stop()
                    if msg[1]:
                        self._bar.config(mode='determinate')
                        self._bar['value'] = 100
                        self._status_label.config(text='完成', fg='#2e7d32')
                    else:
                        self._error_text = msg[2]
                        self._bar.config(mode='determinate')
                        self._bar['value'] = 0
                        self._status_label.config(text='失敗', fg='red')
                        self._error_btn.pack(pady=(4, 0))
                    return

                elif kind == 'done_partial':
                    _, succeeded, total, error_text = msg
                    self._error_text = error_text
                    self._stop_btn.pack_forget()
                    self._bar.stop()
                    self._bar.config(mode='determinate')
                    self._bar['value'] = 100
                    self._status_label.config(
                        text=f'部分失敗 ({succeeded}/{total} 成功)', fg='#e65100')
                    self._error_btn.pack(pady=(4, 0))
                    return

                elif kind == 'done_stop':
                    self._stop_btn.pack_forget()
                    self._bar.stop()
                    self._bar.config(mode='determinate')
                    self._bar['value'] = 0
                    self._status_label.config(text='已中止', fg='#888888')
                    return

        except queue.Empty:
            pass

        self.frame.after(100, self._poll)

    def _update_status(self):
        prefix = f'影片 {self._pl_current}/{self._pl_total} · ' if self._pl_total > 0 else ''
        phase_text = {
            'video':   f'影像串流 {self._current_pct:.0f}%',
            'audio':   f'音訊串流 {self._current_pct:.0f}%',
            'merge':   '合併中...',
            'convert': '轉換中...',
        }.get(self._current_phase, '')
        self._status_label.config(text=f'{prefix}{phase_text}')

    def _show_error(self):
        title = self._title_label.cget('text')
        win   = tk.Toplevel()
        win.title(f'錯誤詳情 - {title}')
        win.geometry('620x400')

        frame = tk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        text   = tk.Text(frame, wrap=tk.WORD, font=('Consolas', 9))
        scroll = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=scroll.set)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text.insert('1.0', self._error_text)
        text.config(state=tk.DISABLED)

        tk.Button(win, text='關閉', command=win.destroy).pack(pady=(0, 8))

    def _stop_download(self):
        self._stop_event.set()
        proc = self._proc_ref[0]
        if proc is not None:
            proc.terminate()
        self._stop_btn.config(state=tk.DISABLED, text='中止中...')

    def _delete(self):
        self._destroyed = True
        self.frame.destroy()


class DownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube 下載器")

        window_width, window_height = 650, 560
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.root.geometry(
            f'{window_width}x{window_height}'
            f'+{int(sw/2 - window_width/2)}+{int(sh/2 - window_height/2)}'
        )

        # ── 輸入區 ──
        inp = tk.Frame(root)
        inp.pack(fill=tk.X, padx=15, pady=(15, 0))

        tk.Label(inp, text="YouTube 網址:").pack(anchor='w')
        self.url_entry = tk.Entry(inp, width=72)
        self.url_entry.pack(fill=tk.X, pady=(2, 8))

        tk.Label(inp, text="輸出格式:").pack(anchor='w')
        self.download_type = tk.StringVar(value="video_best")

        vf = tk.Frame(inp)
        vf.pack(anchor='w', pady=(2, 2))
        tk.Radiobutton(vf, text="影片 - 最高畫質 MP4（含 VP9/AV1）",
                       variable=self.download_type, value="video_best").pack(side=tk.LEFT)
        tk.Radiobutton(vf, text="影片 - 相容模式 MP4（H.264）",
                       variable=self.download_type, value="video_h264").pack(side=tk.LEFT, padx=(10, 0))

        af = tk.Frame(inp)
        af.pack(anchor='w', pady=(0, 8))
        tk.Radiobutton(af, text="音訊 - MP3",
                       variable=self.download_type, value="mp3").pack(side=tk.LEFT)
        tk.Radiobutton(af, text="音訊 - M4A",
                       variable=self.download_type, value="m4a").pack(side=tk.LEFT, padx=(10, 0))

        bot = tk.Frame(inp)
        bot.pack(fill=tk.X, pady=(0, 10))
        tk.Label(bot, text="下載位置:").pack(side=tk.LEFT)
        self.path_entry = tk.Entry(bot, width=44)
        self.path_entry.insert(0, os.getcwd())
        self.path_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(bot, text="瀏覽", command=self.browse_path).pack(side=tk.LEFT)
        tk.Button(bot, text="加入下載", bg="#4CAF50", fg="white",
                  font=("Arial", 10, "bold"),
                  command=self.add_download).pack(side=tk.RIGHT)

        # ── 分隔線 ──
        ttk.Separator(root, orient='horizontal').pack(fill=tk.X, padx=10, pady=(0, 5))

        # ── 清單標題 ──
        tk.Label(root, text="下載清單", font=('Arial', 9, 'bold')).pack(anchor='w', padx=15)

        # ── 可捲動清單 ──
        wrap = tk.Frame(root)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(3, 10))

        self._canvas = tk.Canvas(wrap, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient='vertical', command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas)
        self._cwin  = self._canvas.create_window((0, 0), window=self._inner, anchor='nw')

        self._inner.bind('<Configure>', lambda e: self._canvas.configure(
            scrollregion=(0, 0, e.width, e.height)))
        self._canvas.bind('<Configure>', lambda e: self._canvas.itemconfig(
            self._cwin, width=e.width))
        self._canvas.bind_all('<MouseWheel>', lambda e: self._canvas.yview_scroll(
            int(-1 * (e.delta / 120)), 'units'))

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

    def add_download(self):
        url   = self.url_entry.get().strip()
        path  = self.path_entry.get().strip()
        dtype = self.download_type.get()

        if not url:
            messagebox.showwarning("警告", "請輸入 YouTube 網址")
            return

        DownloadItem(self._inner, url, dtype, path)
        self.url_entry.delete(0, tk.END)


def main():
    root = tk.Tk()
    app  = DownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
