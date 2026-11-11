"""Makes the bharatNova profile picture and 4 highlight covers (run once: python make_assets.py)."""
from PIL import Image, ImageDraw
import bharatnova as B

ASSETS = B.ASSETS
ASSETS.mkdir(exist_ok=True)

# profile picture 1080x1080
im = Image.new("RGBA", (1080, 1080), B.GREEN + (255,))
d = ImageDraw.Draw(im)
for (x, y) in [(250, 300), (830, 250), (900, 760), (220, 820)]:
    d.line((540, 540, x, y), fill=(190, 235, 190, 200), width=8)
    d.ellipse((x - 26, y - 26, x + 26, y + 26), fill=B.GOLD, outline=(255, 255, 255, 255), width=6)
d.ellipse((340, 340, 740, 740), fill=B.CREAM + (255,))
B.text_c(d, 540, 430, B.BRAND_MARK, "black", 230, B.GREEN_D + (255,))
im.convert("RGB").save(ASSETS / "profile_picture.png")

# highlight covers 1080x1920 (same layout as the LexiNode ones, green theme)
covers = [("agri", "कृषी ज्ञान", "रोज नवं शिका", "sprout"), ("products", "उत्पादने", "bharatNova", "wheat"),
          ("organic", "सेंद्रिय शेती", "माती जपा", "sun"), ("water", "पाणी", "थेंब न् थेंब", "drop")]
for key, title, sub, ic in covers:
    c = Image.new("RGBA", (1080, 1920), B.CREAM + (255,))
    d = ImageDraw.Draw(c)
    for x in range(0, 1080, 72):
        d.line((x, 0, x, 1920), fill=(235, 230, 210, 255))
    for y in range(0, 1920, 72):
        d.line((0, y, 1080, y), fill=(235, 230, 210, 255))
    d.ellipse((280, 640, 800, 1160), fill=B.GREEN + (255,))
    B.icon(d, ic, 540, 900, 150, col=(255, 255, 255, 255), col2=B.GOLD)
    B.text_c(d, 540, 1210, title, "black", 120, B.GREEN_D + (255,))
    B.text_c(d, 540, 1370, sub, "med", 56, (120, 130, 110, 255))
    c.convert("RGB").save(ASSETS / f"cover_{key}.png")
print("assets ready")
