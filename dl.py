import sys
import subprocess
import os
import tkinter as tk
from tkinter import filedialog, messagebox

def resource_path(relative_path):
    """ 取得資源絕對路徑 (相容開發環境與 PyInstaller) """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def download_video(url, output_path, download_type):
    """
    下載影片或音訊
    download_type: 'video' 或 'audio'
    """
    try:
        os.makedirs(output_path, exist_ok=True)
        os.chdir(output_path)
        
        yt_dlp_path = resource_path("yt-dlp.exe")
        ffmpeg_path = resource_path("") # ffmpeg.exe 所在目錄
        
        # 基礎指令
        command = [
            yt_dlp_path,
            '--ffmpeg-location', ffmpeg_path,
            '-o', '%(upload_date)s - [%(uploader)s][%(id)s] %(title)s.%(ext)s',
            url
        ]

        # 根據選擇調整參數
        if download_type == 'video':
            # 影片模式：MP4 格式 (H.264 + AAC/M4A)
            command.extend([
                '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
                '--merge-output-format', 'mp4'
            ])
        else:
            # 音訊模式：Opus 編碼，強制封裝入 mp4 容器
            command.extend([
                '--extract-audio',
                '--audio-format', 'opus',
                '--remux-video', 'mp4',  # 強制最終容器為 mp4，這會解決雙重副檔名問題
                '--postprocessor-args', 'ffmpeg:-strict -2'
            ])
        
        # 執行下載
        subprocess.run(command, check=True, capture_output=True, text=True)
        messagebox.showinfo("下載完成", f"檔案已成功下載到:\n{output_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        messagebox.showerror("錯誤", f"下載失敗: {e.stderr}")
        return False
    except Exception as e:
        messagebox.showerror("錯誤", f"發生未知錯誤：{str(e)}")
        return False

class DownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube 下載器")
        
        # 視窗置中設定
        window_width, window_height = 550, 300
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        center_x = int(screen_width/2 - window_width/2)
        center_y = int(screen_height/2 - window_height/2)
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        
        # 1. URL 輸入
        tk.Label(root, text="YouTube 網址:").pack(pady=(15, 0))
        self.url_entry = tk.Entry(root, width=60)
        self.url_entry.pack(pady=5)
        
        # 2. 下載類型選擇 (Radio Buttons)
        tk.Label(root, text="輸出格式:").pack(pady=(10, 0))
        self.download_type = tk.StringVar(value="video") # 預設選中影片
        
        radio_frame = tk.Frame(root)
        radio_frame.pack(pady=5)
        
        self.video_radio = tk.Radiobutton(radio_frame, text="影片 (MP4)", 
                                         variable=self.download_type, value="video")
        self.video_radio.pack(side=tk.LEFT, padx=20)
        
        self.audio_radio = tk.Radiobutton(radio_frame, text="音訊 (Opus in MP4)", 
                                         variable=self.download_type, value="audio")
        self.audio_radio.pack(side=tk.LEFT, padx=20)
        
        # 3. 下載位置
        tk.Label(root, text="下載位置:").pack(pady=(10, 0))
        self.path_frame = tk.Frame(root)
        self.path_frame.pack(pady=5)
        
        self.path_entry = tk.Entry(self.path_frame, width=50)
        self.path_entry.insert(0, os.getcwd())
        self.path_entry.pack(side=tk.LEFT, padx=5)
        
        self.browse_button = tk.Button(self.path_frame, text="瀏覽", command=self.browse_path)
        self.browse_button.pack(side=tk.LEFT)
        
        # 4. 下載按鈕
        self.download_button = tk.Button(root, text="開始下載", bg="#4CAF50", fg="white",
                                        font=("Arial", 10, "bold"), width=20,
                                        command=self.start_download)
        self.download_button.pack(pady=20)

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

    def start_download(self):
        url = self.url_entry.get().strip()
        path = self.path_entry.get().strip()
        dtype = self.download_type.get() # 取得選中的類型 ('video' 或 'audio')
        
        if not url:
            messagebox.showwarning("警告", "請輸入 YouTube 網址")
            return
            
        self.download_button.config(state=tk.DISABLED, text="下載中...")
        self.root.update()
        
        try:
            if download_video(url, path, dtype):
                self.url_entry.delete(0, tk.END)
        finally:
            self.download_button.config(state=tk.NORMAL, text="開始下載")

def main():
    root = tk.Tk()
    # 如果你有圖標，可以在這裡加入：
    # try: root.iconbitmap(resource_path("icon.ico")) except: pass
    app = DownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()