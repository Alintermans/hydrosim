"""HydroTeam V0 livery for gtp_radical_rxc_gt3, on top of the HT_Themed skin.
UV zones and text orientation measured from the 00_Skittles skin."""
from PIL import Image, ImageDraw
A = 'assets/'
NAVY = (2, 30, 55)

base = Image.open('ht_body_dds.png').convert('RGBA')
alpha = base.getchannel('A')
canvas = base.convert('RGB').convert('RGBA')

def load(n):
    return Image.open(A + n + '.png').convert('RGBA')

def recolor(im, rgb):
    out = Image.new('RGBA', im.size, rgb + (0,))
    out.putalpha(im.getchannel('A'))
    return out

def place(im, cx, cy, length, rot, mirror=True):
    """length = size along the text direction (px on the texture)."""
    im = im.copy()
    s = length / im.width
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    for x, r in [(cx, rot)] + ([(4096 - cx, {-90: 90, 90: -90}.get(rot, rot))] if mirror else []):
        r_im = im.rotate(r, expand=True, resample=Image.BICUBIC)
        canvas.alpha_composite(r_im, (int(x - r_im.width / 2), int(cy - r_im.height / 2)))

def flag():
    f = Image.new('RGBA', (320, 220), (255, 255, 255, 255))   # thin white edge
    d = ImageDraw.Draw(f)
    for i, c in enumerate([(0, 0, 0), (253, 218, 36), (239, 51, 64)]):
        d.rectangle([10 + i * 100, 10, 10 + i * 100 + 99, 209], fill=c + (255,))
    return f

num = load('num56')
ht_w, ht_c, kul = load('ht_white'), load('ht_color'), load('kul')
P = {n: load('p_' + n) for n in ['agoria', 'belden', 'van-mossel', 'domec', 'fike',
     'phoenix-contact', 'airtech', 'vincotte', 'atlas-copco', 'air-products', 'elneo',
     'ventrex', 'bindsol', 'thrustmaster']}
navy = {k: recolor(v, NAVY) for k, v in P.items()}

# --- sides (left; mirrored to the right) -----------------------------------
place(ht_w, 790, 2175, 560, -90)                 # HydroTeam wordmark, main side spot
place(num, 800, 1700, 330, -90)                  # race number ahead of it
place(flag(), 650, 1590, 80, -90)                # Belgian flag
place(navy['agoria'], 1040, 2280, 380, -90)      # upper side (sky band)
# sill strip (sky): small navy partner logos along its centre line
for i, (n, ln) in enumerate([('thrustmaster', 200), ('elneo', 150), ('air-products', 190), ('ventrex', 200)]):
    t = (i + 0.5) / 4
    y = 1640 + t * 820
    x = 566 - (y - 1597) * (72 / 914)
    place(navy[n], x, y, ln, -90)
# --- rear panels -----------------------------------------------------------
for i, (l, r) in enumerate([('van-mossel', 'phoenix-contact'), ('domec', 'belden'), ('bindsol', 'atlas-copco')]):
    y = 2760 + i * 215
    place(P[l], 235, y, 190, -90, mirror=False)
    place(P[r], 4096 - 235, y, 190, 90, mirror=False)
# --- wing endplates (sky) and front fenders (dark) ---------------------------
place(navy['fike'], 420, 560, 210, 180, mirror=False)
place(navy['airtech'], 4096 - 420, 560, 210, 180, mirror=False)
place(P['vincotte'], 1010, 640, 120, 180)
# --- hood + sunstrip -------------------------------------------------------
place(num, 2048, 560, 300, 180, mirror=False)
place(kul, 2048, 800, 380, 180, mirror=False)
place(ht_w, 2048, 1622, 640, 180, mirror=False)

out = canvas.convert('RGB')
out.putalpha(alpha)
out.save('hydroteam_body.png')
prev = out.convert('RGB'); prev.thumbnail((1400, 1400))
prev.save('/home/u0160776/.playwright-mcp/livery/v0_body.jpg', quality=88)
print('ok')
