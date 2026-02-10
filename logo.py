from PIL import Image
import os

def png_to_ico(png_path, ico_path, icon_sizes=None):
    icon_sizes = icon_sizes or [(256, 256)]  # 預設生成16x16、32x32、64x64大小的ICO檔案
    img = Image.open(png_path)

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    ico_images = []
    for size in icon_sizes:
        img_resized = img.resize(size)
        ico_images.append(img_resized)

    ico_path = os.path.abspath(ico_path)
    img.save(ico_path, format="ICO", sizes=[(img.width, img.height) for img in ico_images])

if __name__ == "__main__":
    png_file = "logo.png"  # 輸入的PNG檔案路徑
    ico_file = "icon.ico"  # 輸出的ICO檔案路徑
    png_to_ico(png_file, ico_file)