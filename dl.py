import sys
import subprocess
import os
import re
import threading
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.ttk as ttk
import tkinter.font as tkFont
import sv_ttk

CARD_BG = '#ffffff'
BORDER  = '#e0e0e0'
FONT    = 'Segoe UI'

BADGE_CFG = {
    'video_best': ('#dce8fb', '#1a5fc8'),
    'video_h264': ('#dce8fb', '#1a5fc8'),
    'm4a':        ('#dff0e0', '#1e7a34'),
}

PCT_PATTERN      = re.compile(r'\[download\]\s+([\d.]+)%')
PLAYLIST_PATTERN = re.compile(r'\[download\] Downloading (?:video|item) (\d+) of (\d+)')

TYPE_LABELS = {
    'video_best': '影片 - 最高畫質',
    'video_h264': '影片 - 相容模式',
    'm4a':        '音訊 - M4A',
}

def _get_bg(widget):
    if isinstance(widget, ttk.Widget):
        return ttk.Style().lookup('TFrame', 'background') or '#f3f3f3'
    for key in ('bg', 'background'):
        try:
            val = str(widget.cget(key)).strip()
            if val:
                return val
        except tk.TclError:
            pass
    return ttk.Style().lookup('TFrame', 'background') or '#f3f3f3'


class RoundedButton(tk.Canvas):
    _COLORS = {
        'blue':   ('#0078d4', '#005a9e'),
        'red':    ('#c42b1c', '#a02216'),
        'orange': ('#c55a00', '#a04800'),
        'green':  ('#107c10', '#0a5e0a'),
    }

    def __init__(self, parent, text, color, command, height=28, radius=8):
        self._c_normal, self._c_hover = self._COLORS[color]
        self._cmd     = command
        self._text    = text
        self._radius  = radius
        self._h       = height
        self._enabled = True

        _font = tkFont.Font(family=FONT, size=9)
        self._btn_w = _font.measure(text) + 28

        bg = _get_bg(parent)
        super().__init__(parent, width=self._btn_w, height=height,
                         bg=bg, highlightthickness=0, cursor='hand2')

        self._draw(self._c_normal)
        self.bind('<Enter>', lambda e: self._draw(self._c_hover) if self._enabled else None)
        self.bind('<Leave>', lambda e: self._draw(self._c_normal) if self._enabled else None)
        self.bind('<Button-1>', lambda e: self._cmd() if self._enabled else None)

    def _draw(self, fill):
        self.delete('all')
        r, w, h = self._radius, self._btn_w, self._h
        self.create_arc(0,     0,     2*r,   2*r,   start=90,  extent=90, fill=fill, outline=fill)
        self.create_arc(w-2*r, 0,     w,     2*r,   start=0,   extent=90, fill=fill, outline=fill)
        self.create_arc(0,     h-2*r, 2*r,   h,     start=180, extent=90, fill=fill, outline=fill)
        self.create_arc(w-2*r, h-2*r, w,     h,     start=270, extent=90, fill=fill, outline=fill)
        self.create_rectangle(r, 0,   w-r, h,   fill=fill, outline=fill)
        self.create_rectangle(0, r,   w,   h-r, fill=fill, outline=fill)
        self.create_text(w//2, h//2, text=self._text, fill='white', font=(FONT, 9))

    def config(self, **kw):
        state = kw.pop('state', None)
        text  = kw.pop('text', None)
        if state is not None:
            self._enabled = (state != tk.DISABLED)
            super().config(cursor='' if not self._enabled else 'hand2')
            self._draw(self._c_normal if self._enabled else '#aaaaaa')
        if text is not None:
            self._text = text
            _font = tkFont.Font(family=FONT, size=9)
            self._btn_w = _font.measure(text) + 28
            super().config(width=self._btn_w)
            self._draw(self._c_normal if self._enabled else '#aaaaaa')
        if kw:
            super().config(**kw)

    configure = config


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
            '--split-chapters',
            '-o', '%(upload_date)s - [%(uploader)s][%(id)s] %(title)s.%(ext)s',
            '-o', 'chapter:%(upload_date)s - [%(uploader)s][%(id)s] %(section_title)s.%(ext)s',
            url
        ]

        is_video = download_type in ('video_h264', 'video_best')

        if download_type == 'video_h264':
            command.extend(['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4', '--merge-output-format', 'mp4'])
        elif download_type == 'video_best':
            command.extend(['-f', 'bestvideo+bestaudio/best', '--merge-output-format', 'mp4'])
        elif download_type == 'm4a':
            command.extend(['--extract-audio', '--audio-format', 'm4a'])

        phase          = None
        dest_count     = 0
        is_playlist    = False
        current_video  = 0
        total_videos   = 0
        title_sent     = False
        stderr_lines   = []
        error_segments = []

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

            if line.startswith('ERROR:'):
                if is_playlist:
                    error_segments.append((current_video, line))
                continue

            if '[download] Destination:' in line:
                dest_count += 1
                filename = line.split('[download] Destination:', 1)[1].strip()

                if not title_sent or is_playlist:
                    parts = filename.rsplit('] ', 1)
                    if len(parts) == 2:
                        raw_title = parts[1]
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

            if '[SplitChapters]' in line:
                phase = 'split'
                q.put(('phase', 'split'))
                continue

            if '[Merger]' in line:
                q.put(('progress', 'audio', 100.0))
                phase = 'merge'
                q.put(('phase', 'merge'))
                continue

            if '[ExtractAudio]' in line:
                q.put(('progress', 'audio', 100.0))
                phase = 'convert'
                q.put(('phase', 'convert'))
                continue

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
        self.frame = tk.Frame(
            parent,
            bg=CARD_BG,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        self.frame.pack(fill=tk.X, padx=6, pady=3)

        # ── 左側：徽章 + 標題 + URL ──
        left = tk.Frame(self.frame, bg=CARD_BG)
        left.grid(row=0, column=0, sticky='nsew', padx=(10, 6), pady=8)

        top_row = tk.Frame(left, bg=CARD_BG)
        top_row.pack(anchor='w', fill=tk.X)

        bbg, bfg = BADGE_CFG.get(self._download_type, ('#f0f0f0', '#555555'))
        tk.Label(
            top_row,
            text=TYPE_LABELS.get(self._download_type, ''),
            bg=bbg, fg=bfg,
            font=(FONT, 8),
            padx=6, pady=2,
            relief=tk.FLAT
        ).pack(side=tk.LEFT)

        self._title_label = tk.Label(
            top_row,
            text=self._url,
            bg=CARD_BG, fg='#1a1a1a',
            font=(FONT, 9, 'bold'),
            anchor='w'
        )
        self._title_label.pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(
            left,
            text=self._url,
            bg=CARD_BG, fg='#888888',
            font=(FONT, 8),
            anchor='w'
        ).pack(anchor='w', pady=(3, 0))

        # ── 右側：進度條 + 狀態 + 按鈕 ──
        right = tk.Frame(self.frame, bg=CARD_BG)
        right.grid(row=0, column=1, sticky='ns', padx=(0, 10), pady=8)

        self._bar = ttk.Progressbar(right, length=200, mode='determinate', maximum=100)
        self._bar.pack()

        self._status_label = tk.Label(
            right,
            text='準備中',
            bg=CARD_BG, fg='#888888',
            font=(FONT, 8),
            width=22
        )
        self._status_label.pack(pady=(3, 0))

        self._stop_btn = RoundedButton(right, '中止', 'red', self._stop_download)
        self._stop_btn.pack(pady=(5, 0))

        self._error_btn = RoundedButton(right, '查看錯誤', 'orange', self._show_error)

        # ── 右上角：複製 + 刪除 ──
        corner = tk.Frame(self.frame, bg=CARD_BG)
        corner.grid(row=0, column=2, sticky='ne', padx=(0, 6), pady=(4, 0))

        tk.Button(
            corner, text='⧉',
            bg=CARD_BG, fg='#aaaaaa',
            activebackground=CARD_BG, activeforeground='#555555',
            font=(FONT, 12), relief=tk.FLAT, bd=0, cursor='hand2',
            command=self._copy_url
        ).pack(side=tk.LEFT)

        tk.Button(
            corner, text='✕',
            bg=CARD_BG, fg='#bbbbbb',
            activebackground=CARD_BG, activeforeground='#555555',
            font=(FONT, 10), relief=tk.FLAT, bd=0, cursor='hand2',
            command=self._delete
        ).pack(side=tk.LEFT)

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
                    if msg[1] in ('merge', 'convert', 'split'):
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
                        self._status_label.config(text='完成', fg='#107c10')
                    else:
                        self._error_text = msg[2]
                        self._bar.config(mode='determinate')
                        self._bar['value'] = 0
                        self._status_label.config(text='失敗', fg='#c42b1c')
                        self._error_btn.pack(pady=(5, 0))
                    return

                elif kind == 'done_partial':
                    _, succeeded, total, error_text = msg
                    self._error_text = error_text
                    self._stop_btn.pack_forget()
                    self._bar.stop()
                    self._bar.config(mode='determinate')
                    self._bar['value'] = 100
                    self._status_label.config(
                        text=f'部分失敗 ({succeeded}/{total} 成功)', fg='#9d5d00')
                    self._error_btn.pack(pady=(5, 0))
                    return

                elif kind == 'done_stop':
                    self._stop_btn.pack_forget()
                    self._bar.stop()
                    self._bar.config(mode='determinate')
                    self._bar['value'] = 0
                    self._status_label.config(text='已中止', fg='#767676')
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
            'split':   '切割章節中...',
        }.get(self._current_phase, '')
        self._status_label.config(text=f'{prefix}{phase_text}', fg='#555555')

    def _show_error(self):
        title = self._title_label.cget('text')
        win   = tk.Toplevel()
        win.title(f'錯誤詳情 - {title}')
        win.geometry('660x420')

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 6))

        text = tk.Text(
            frame,
            wrap=tk.WORD,
            font=('Consolas', 9),
            bg=CARD_BG, fg='#1a1a1a',
            relief=tk.FLAT, bd=0,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        scroll = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=scroll.set)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text.insert('1.0', self._error_text)
        text.config(state=tk.DISABLED)

        RoundedButton(win, '關閉', 'blue', win.destroy).pack(pady=(0, 10))

    def _stop_download(self):
        self._stop_event.set()
        proc = self._proc_ref[0]
        if proc is not None:
            proc.terminate()
        self._stop_btn.config(state=tk.DISABLED, text='中止中...')

    def _copy_url(self):
        self.frame.clipboard_clear()
        self.frame.clipboard_append(self._url)

    def _delete(self):
        self._destroyed = True
        self.frame.destroy()


class DownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube 下載器 v26.6.1")

        window_width, window_height = 660, 560
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.root.geometry(
            f'{window_width}x{window_height}'
            f'+{int(sw/2 - window_width/2)}+{int(sh/2 - window_height/2)}'
        )

        # 取得 sv_ttk 套用後的實際背景色，用於 canvas 等非 ttk 元件
        theme_bg = ttk.Style().lookup('TFrame', 'background') or '#f9f9f9'

        # ── 輸入區 ──
        inp = ttk.Frame(root)
        inp.pack(fill=tk.X, padx=16, pady=(16, 0))

        ttk.Label(inp, text="YouTube 網址").pack(anchor='w')
        self.url_entry = ttk.Entry(inp, font=(FONT, 10))
        self.url_entry.pack(fill=tk.X, pady=(3, 10))

        ttk.Label(inp, text="輸出格式").pack(anchor='w')
        self.download_type = tk.StringVar(value="video_best")

        vf = ttk.Frame(inp)
        vf.pack(anchor='w', pady=(3, 2))
        ttk.Radiobutton(vf, text="影片 - 最高畫質 MP4（含 VP9/AV1）",
                        variable=self.download_type, value="video_best").pack(side=tk.LEFT)
        ttk.Radiobutton(vf, text="影片 - 相容模式 MP4（H.264）",
                        variable=self.download_type, value="video_h264").pack(side=tk.LEFT, padx=(12, 0))

        af = ttk.Frame(inp)
        af.pack(anchor='w', pady=(0, 10))
        ttk.Radiobutton(af, text="音訊 - M4A",
                        variable=self.download_type, value="m4a").pack(side=tk.LEFT)

        bot = ttk.Frame(inp)
        bot.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(bot, text="下載位置").pack(side=tk.LEFT)
        self.path_entry = ttk.Entry(bot, font=(FONT, 9))
        self.path_entry.insert(0, os.getcwd())
        self.path_entry.pack(side=tk.LEFT, padx=(8, 6), fill=tk.X, expand=True)
        RoundedButton(bot, "瀏覽", 'blue', self.browse_path).pack(side=tk.LEFT)
        RoundedButton(bot, "加入下載", 'blue', self.add_download).pack(side=tk.RIGHT, padx=(12, 0))

        # ── 分隔線 ──
        ttk.Separator(root, orient='horizontal').pack(fill=tk.X, padx=12, pady=(0, 4))

        # ── 清單標題 ──
        ttk.Label(root, text="下載清單", font=(FONT, 9, 'bold')).pack(
            anchor='w', padx=16, pady=(6, 4))

        # ── 可捲動清單 ──
        wrap = ttk.Frame(root)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._canvas = tk.Canvas(wrap, highlightthickness=0, bg=theme_bg)
        sb = ttk.Scrollbar(wrap, orient='vertical', command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, bg=theme_bg)
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
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    sv_ttk.set_theme('light')

    try:
        root.iconbitmap(resource_path('icon.ico'))
    except Exception:
        pass

    app  = DownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
