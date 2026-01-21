import sys
import subprocess
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
import pkg_resources

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def download_video(url, output_path='.'):
    try:
        # 確保輸出路徑存在
        os.makedirs(output_path, exist_ok=True)
        
        # 切換到指定的輸出路徑
        os.chdir(output_path)
        
        # 取得 yt-dlp 的路徑
        yt_dlp_path = resource_path("yt-dlp.exe")
        
        # 修改後的下載參數
        command = [
            yt_dlp_path,
            '--ffmpeg-location', resource_path(""),  # 指定 ffmpeg 路徑
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',  # 指定格式
            '--merge-output-format', 'mp4',  # 指定合併格式
            '--no-keep-video',  # 不保留原始檔案
            '--no-keep-fragments',  # 不保留片段
            '-o', '%(upload_date)s - [%(uploader)s][%(id)s] %(title)s.%(ext)s',
            url
        ]
        
        # 執行下載
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        
        # 顯示成功訊息
        messagebox.showinfo("下載完成", f"影片已成功下載到:\n{output_path}")
        
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
        
        # 設定視窗大小和位置
        window_width = 500
        window_height = 200
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        center_x = int(screen_width/2 - window_width/2)
        center_y = int(screen_height/2 - window_height/2)
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        
        # URL 輸入
        tk.Label(root, text="YouTube 網址:").pack(pady=5)
        self.url_entry = tk.Entry(root, width=50)
        self.url_entry.pack(pady=5)
        
        # 下載位置
        tk.Label(root, text="下載位置:").pack(pady=5)
        self.path_frame = tk.Frame(root)
        self.path_frame.pack(pady=5)
        
        self.path_entry = tk.Entry(self.path_frame, width=40)
        self.path_entry.insert(0, os.getcwd())  # 預設為目前目錄
        self.path_entry.pack(side=tk.LEFT, padx=5)
        
        self.browse_button = tk.Button(self.path_frame, text="瀏覽", command=self.browse_path)
        self.browse_button.pack(side=tk.LEFT)
        
        # 下載按鈕
        self.download_button = tk.Button(root, text="下載", command=self.start_download)
        self.download_button.pack(pady=20)

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

    def start_download(self):
        url = self.url_entry.get().strip()
        path = self.path_entry.get().strip()
        
        if not url:
            messagebox.showwarning("警告", "請輸入 YouTube 網址")
            return
            
        if not path:
            path = os.getcwd()
            
        # 禁用按鈕避免重複點擊
        self.download_button.config(state=tk.DISABLED)
        self.root.update()
        
        try:
            if download_video(url, path):
                # 清空輸入框
                self.url_entry.delete(0, tk.END)
        finally:
            # 重新啟用按鈕
            self.download_button.config(state=tk.NORMAL)

def main():
    root = tk.Tk()
    app = DownloaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()