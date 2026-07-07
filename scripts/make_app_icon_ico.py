"""Generate app_icon.ico from app_icon.png for Windows PyInstaller builds."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
png = ROOT / "MegaSerial" / "resources" / "app_icon.png"
ico = ROOT / "MegaSerial" / "resources" / "app_icon.ico"

img = Image.open(png).convert("RGBA")
sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
img.save(ico, format="ICO", sizes=sizes)
print(f"Wrote {ico}")
