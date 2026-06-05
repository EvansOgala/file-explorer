@echo off
setlocal

py -m pip install --upgrade pip pyinstaller
py -m pip install PySide6
py -m pip install Pillow

if not exist "app_icon.ico" (
  py -c "from PIL import Image, ImageDraw; im=Image.new('RGBA',(256,256),(43,124,255,255)); d=ImageDraw.Draw(im); d.rounded_rectangle((20,46,236,220), radius=22, fill=(32,43,70,255)); d.rectangle((20,72,236,98), fill=(255,255,255,220)); d.rectangle((38,110,120,182), fill=(255,255,255,220)); d.rectangle((136,110,218,182), fill=(255,255,255,220)); im.save('app_icon.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
)

py -m PyInstaller --noconfirm --clean FileExplorer.spec

echo.
echo Build complete. Output: dist\FileExplorer\
endlocal
