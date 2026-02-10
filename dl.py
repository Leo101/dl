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
    try:
        os.makedirs(output_path, exist_ok=True)
        os.chdir(output_path)
        
        yt_dlp_path = resource_path("yt-dlp.exe")
        ffmpeg_path = resource_path("") 

        # 基礎指令
        command = [
            yt_dlp_path,
            '--ffmpeg-location', ffmpeg_path,
            '-o', '%(upload_date)s - [%(uploader)s][%(id)s] %(title)s.%(ext)s',
            url
        ]

        # 根據選項決定參數
        if download_type == 'video_mp4':
            command.extend([
                '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
                '--merge-output-format', 'mp4'
            ])
        elif download_type == 'audio_opus':
            command.extend(['--extract-audio', '--audio-format', 'opus'])
        elif download_type == 'audio_m4a':
            command.extend(['--extract-audio', '--audio-format', 'm4a'])
        elif download_type == 'audio_mp3':
            command.extend(['--extract-audio', '--audio-format', 'mp3', '--audio-quality', '0'])
        
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
        self.root.geometry("600x350")
        
        # 1. URL 輸入
        tk.Label(root, text="YouTube 網址:").pack(pady=(15, 0))
        self.url_entry = tk.Entry(root, width=70)
        self.url_entry.pack(pady=5)
        
        # 2. 輸出格式選擇 (四個選項)
        tk.Label(root, text="選擇輸出格式:").pack(pady=(10, 0))
        self.download_type = tk.StringVar(value="video_mp4")
        
        radio_frame = tk.Frame(root)
        radio_frame.pack(pady=5)
        
        # 第一排：影片
        tk.Radiobutton(radio_frame, text="影片 (MP4)", variable=self.download_type, 
                       value="video_mp4").grid(row=0, column=0, padx=10, sticky="w")
        
        # 第二排：音訊選項
        tk.Radiobutton(radio_frame, text="音訊 (Opus)", variable=self.download_type, 
                       value="audio_opus").grid(row=1, column=0, padx=10, pady=5)
        tk.Radiobutton(radio_frame, text="音訊 (M4A)", variable=self.download_type, 
                       value="audio_m4a").grid(row=1, column=1, padx=10, pady=5)
        tk.Radiobutton(radio_frame, text="音訊 (MP3)", variable=self.download_type, 
                       value="audio_mp3").grid(row=1, column=2, padx=10, pady=5)
        
        # 3. 下載位置
        tk.Label(root, text="下載位置:").pack(pady=(10, 0))
        self.path_frame = tk.Frame(root)
        self.path_frame.pack(pady=5)
        
        self.path_entry = tk.Entry(self.path_frame, width=50)
        self.path_entry.insert(0, os.getcwd())
        self.path_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Button(self.path_frame, text="瀏覽", command=self.browse_path).pack(side=tk.LEFT)
        
        # 4. 下載按鈕
        self.download_button = tk.Button(root, text="開始下載", bg="#4CAF50", fg="white", 
                                        font=("Arial", 10, "bold"), width=20, 
                                        command=self.start_download)
        self.download_button.pack(pady=25)

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

    def start_download(self):
        url = self.url_entry.get().strip()
        path = self.path_entry.get().strip()
        dtype = self.download_type.get()
        
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

if __name__ == "__main__":
    root = tk.Tk()
    try:
        root.iconbitmap(resource_path("icon.ico"))
    except:
        pass
    app = DownloaderGUI(root)
    root.mainloop()