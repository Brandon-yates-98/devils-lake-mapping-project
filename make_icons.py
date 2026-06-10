"""Generate PWA icons from the Apex logo on the app's dark background.

Logo is sized to ~60% of the canvas so the icons survive iOS rounded
corners and Android maskable cropping. Run: python make_icons.py
"""
from PIL import Image

BG = (10, 20, 10, 255)  # #0a140a — matches the app background
SIZES = [512, 192, 180]

logo = Image.open("docs/icons/_logo_src.png").convert("RGBA")

for size in SIZES:
    canvas = Image.new("RGBA", (size, size), BG)
    target = int(size * 0.62)
    scale = min(target / logo.width, target / logo.height)
    resized = logo.resize((int(logo.width * scale), int(logo.height * scale)), Image.LANCZOS)
    canvas.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    canvas.convert("RGB").save(f"docs/icons/icon-{size}.png", "PNG")
    print(f"docs/icons/icon-{size}.png")
