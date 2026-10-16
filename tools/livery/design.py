"""HydroTeam V0 livery, designed in 3D: every texel knows where it sits on
the car (uvbake.npz), so stripes run continuously across panels and decals
are projected straight onto the body like real stickers.

Car frame (AC, left-handed): x = right (looking forward), y = up, z = forward.
Front axle z~+1.2, rear axle z~-1.5, sides at |x|~0.97, roof y~1.15."""
import numpy as np
from PIL import Image, ImageDraw

S = 4096
d = np.load('uvbake.npz')
M = d['mask']
P = d['pos'][M].astype(np.float32)
N = d['nrm'][M].astype(np.float32)
x, y, z = P[:, 0], P[:, 1], P[:, 2]
nx, ny, nz = N[:, 0], N[:, 1], N[:, 2]

def rgb(h): return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
BLUE, SKY, ORANGE = rgb('#1C76CF'), rgb('#5CC6F0'), rgb('#E2621F')
NAVY, WHITE = rgb('#0B1F38'), rgb('#FFFFFF')

col = np.tile(BLUE, (len(x), 1))

def paint(sel, c):
    col[sel] = c

def smooth(a, b, t):
    t = np.clip((t - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)

side = np.abs(nx) > 0.35
ax = np.abs(x)

# --- 1. lower sweep (sky) with orange pinstripe ------------------------------
# A curve along the flanks: high over the front fender, dips under the door,
# kicks up over the rear haunch -- the V0's light-blue lower fenders.
def sweep_y(zz):
    base = 0.25 + 0.10 * smooth(0.7, 2.0, zz)            # a touch higher at the nose
    rear = 0.20 * smooth(-1.15, -1.45, zz)               # kicks up at the rear arch
    return base + rear
sy = sweep_y(z)
f_sweep = y - sy
low = (f_sweep < 0) & (ax > 0.25)
paint(low, SKY)
paint((np.abs(f_sweep) < 0.012) & (ax > 0.25), ORANGE)

# --- 2. sill + splitter + diffuser: navy, with a sky line above --------------
sill = (y < 0.17) & side
paint(sill | (y < 0.13), NAVY)
paint((np.abs(y - 0.17) < 0.008) & side, WHITE)

# --- 2b. brand band: navy along the flank between the wheels (the V0's dark
# sill), carrying a big white HydroTeam wordmark ---------------------------
# The whole flat flank below the ledge (y < 0.53) between the wheels goes
# navy: a dark lower body under the blue top, and every logo sits white on
# dark -- maximum contrast, like a prototype's sponsor flank.
flank = (np.abs(nx) > 0.45) & (ax > 0.6) & (z < 0.80) & (z > -1.17) & (y > 0.09)
paint(flank & (y < 0.528), NAVY)
paint(flank & (y >= 0.528) & (y < 0.540), ORANGE)
paint(flank & (y >= 0.540) & (y < 0.552), SKY)

# --- 3. rear deck sky, outlined in orange -------------------------------------
wing = (y > 0.93) & (z < -1.72)
deck = (ny > 0.55) & (z < -0.45) & (y > 0.6) & ~wing
f_deck = z + 0.45
paint(deck, SKY)
paint((ny > 0.55) & (np.abs(f_deck) < 0.012) & (y > 0.6), ORANGE)

paint(wing, NAVY)

# --- 4. nose: sky chevron flanking the centre, orange inner edge -------------
nose = (z > 0.55) & (ny > 0.25)
cx = 0.42 - 0.12 * smooth(0.6, 2.1, z)                  # chevron edge position
f_chev = ax - cx
paint(nose & (f_chev > 0) & (f_chev < 0.16), SKY)
paint(nose & (np.abs(f_chev) < 0.012), ORANGE)

# --- 4b. orange patches on the front-fender tops (V0 signature) -------------
fpatch = (ny > 0.45) & (z > 0.92) & (z < 1.5) & (ax > 0.52) & (ax < 0.92)
paint(fpatch, ORANGE)

# --- 5. speed stripes ahead of the rear wheel (the V0 signature) -------------
lean = 0.55
t = (z - lean * y)                                       # slanted coordinate
zone = (np.abs(nx) > 0.3) & (ax > 0.45) & (y > 0.6) & (t > -1.75) & (t < -1.05) & (y > sy + 0.02) & (y < 0.86)
band = np.floor((t + 1.75) / 0.1).astype(int)
phase = ((t + 1.75) / 0.1) % 1
cyc = [ORANGE, BLUE, ORANGE, SKY, ORANGE, BLUE, ORANGE]
for i, c in enumerate(cyc):
    paint(zone & (band == i) & (phase > 0.1), c)
paint(zone & (phase <= 0.1), NAVY)

# --- decals ------------------------------------------------------------------
def load(n, color=None):
    im = Image.open('assets/' + n + '.png').convert('RGBA')
    a = np.asarray(im).astype(np.float32) / 255
    if color is not None:
        a = np.concatenate([np.broadcast_to(color, a.shape[:2] + (3,)), a[..., 3:]], -1)
    return a

def stamp(img, sel, u, v):
    h, w = img.shape[:2]
    ok = sel & (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    px = img[(v[ok] * h).astype(int), (u[ok] * w).astype(int)]
    a = px[:, 3:4]
    col[ok] = col[ok] * (1 - a) + px[:, :3] * a

def side_decal(img, zc, yc, width, both=True, min_ax=0.6):
    h = width * img.shape[0] / img.shape[1]
    for s in ((1, -1) if both else (1,)):
        sel = (s * nx > 0.25) & (s * x > min_ax)
        u = 0.5 - s * (z - zc) / width          # reads left-to-right from outside
        v = 0.5 - (y - yc) / h
        stamp(img, sel, u, v)

def top_decal(img, xc, zc, width, from_front=False, mirror_x=False, ymin=0.3, ymax=9.0):
    h = width * img.shape[0] / img.shape[1]
    sel = (ny > 0.35) & (y > ymin) & (y < ymax)
    for xx in ((xc, -xc) if mirror_x else (xc,)):
        if from_front:
            u = 0.5 + (x - xx) / width; v = 0.5 + (z - zc) / h
        else:   # readable from the driver's seat
            u = 0.5 - (x - xx) / width; v = 0.5 - (z - zc) / h
        stamp(img, sel, u, v)

W = WHITE
side_decal(load('ht_white'), -0.18, 0.163, 0.92)                 # HydroTeam, big, on the navy band
side_decal(load('num56w'), -0.46, 0.705, 0.235, min_ax=0.45)  # upper rear quarter, above the ledge                     # 56 on the door
flag = np.zeros((40, 60, 4), np.float32); flag[..., 3] = 1
flag[:, :20, :3] = 0; flag[:, 20:40, :3] = rgb('#FDDA24'); flag[:, 40:, :3] = rgb('#EF3340')
side_decal(flag, -0.66, 0.70, 0.075, min_ax=0.45)
# Partners: every logo gets the SAME optical size -- equal area, capped so
# very wide or tall marks stay in proportion -- on a tidy grid.
AREA, MAX_W, MAX_H = 0.0195, 0.205, 0.092

def partner(name, zc, yc, navy=False, min_ax=0.55, max_w=None):
    img = load(name, NAVY if navy else None)
    if name != 'p_vincotte':  # light-grey parts of a logo become solid too
        img[..., 3] = np.clip(img[..., 3] * 1.8, 0, 1)
    aspect = img.shape[1] / img.shape[0]
    w = (AREA * aspect) ** 0.5
    w = min(w, max_w or MAX_W, MAX_H * aspect)
    side_decal(img, zc, yc, w, min_ax=min_ax)

# THE 12 MAIN PARTNERS, all on the flanks (what visitors at the stand see,
# and what the AC start-menu camera shows), white on blue for contrast.
import os
from PIL import ImageFilter

def bold(img):
    # thicken thin strokes a little so light fonts stay legible
    a = Image.fromarray((img[..., 3] * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
    img = img.copy(); img[..., 3] = np.asarray(a).astype(np.float32) / 255
    return img

def partner2(name, zc, yc, keep_colour=False, max_w=None, max_h=None, boost=1.0):
    if not os.path.exists('assets/' + name + '.png'):
        return False  # slot kept free until the logo file arrives
    img = load(name)
    if not keep_colour:
        img[..., :3] = 1.0
        img[..., 3] = np.clip(img[..., 3] * 1.8, 0, 1)
        img = bold(img)
    aspect = img.shape[1] / img.shape[0]
    w = min((AREA * aspect) ** 0.5 * boost, max_w or MAX_W, (max_h or MAX_H) * aspect)  # never wider than its cell
    side_decal(img, zc, yc, w, min_ax=0.5)
    return True

# The flat, vertical flank (y 0.26..0.52, z +0.5..-1.25) is the billboard:
# 12 partners on a 2 x 6 grid, white on blue (Ford, Vincotte, NRF in colour).
COLS = [0.33, 0.08, -0.17, -0.42, -0.67, -0.92]
ROW1 = ['p_agoria', 'p_ford', 'p_fike', 'p_atlas-copco', 'p_air-products', 'p_belden']
ROW2 = ['p_vincotte', 'p_bindsol', 'p_ocas', 'p_elneo', 'p_nrf', 'p_burke-porter']
COLOUR = {'p_vincotte', 'p_nrf'}
for row_y, names in ((0.445, ROW1), (0.33, ROW2)):
    for zc, n in zip(COLS, names):
        boost = {'p_air-products': 1.25, 'p_atlas-copco': 1.25, 'p_ocas': 1.25, 'p_vincotte': 1.2}.get(n, 1.0)
        partner2(n, zc, row_y, keep_colour=n in COLOUR, boost=boost,
                 max_h=0.115 if n == 'p_vincotte' else None)
top_decal(load('ht_mark', W), 0.0, 1.78, 0.42, ymin=0.3)        # nose
top_decal(load('kul'), 0.0, 1.35, 0.46)                         # hood
top_decal(load('num56w'), 0.0, -0.25, 0.40, ymin=1.0)           # roof, for the TV camera
top_decal(load('ht_white'), 0.0, -2.0, 1.2, ymin=0.93)          # wing, reads from the chase cam
top_decal(load('p_fike'), 0.72, 1.22, 0.24, mirror_x=True, ymin=0.45)

top_decal(load('ht_white'), 0.48, 2.0, 0.55, from_front=True, mirror_x=True, ymin=0.0, ymax=0.15)  # splitter

# --- shading: keep the original panel lines / AO, and the silver details -----
ht_png = np.asarray(Image.open('car/skins/HT_Themed/body.png').convert('RGB')).astype(np.float32)[M] / 255
ht_dds = np.asarray(Image.open('ht_body_dds.png').convert('RGBA')).astype(np.float32)[M] / 255
L = ht_png @ np.array([0.3, 0.59, 0.11], np.float32)
ao = np.clip(L / np.median(L[L > 0.05]), 0.15, 1.15)[:, None]
out_rgb = col * ao
c = ht_dds[:, :3]
mx, mn = c.max(1), c.min(1)
silver = ((mx - mn) < 0.12 * np.maximum(mx, 1e-3)) & (mx > 0.35)
dark = mx < 0.05
out_rgb[silver | dark] = c[silver | dark]

full = np.asarray(Image.open('ht_body_dds.png').convert('RGBA')).astype(np.float32) / 255
full[M, :3] = out_rgb
img = Image.fromarray((np.clip(full, 0, 1) * 255).astype(np.uint8), 'RGBA')
img.save('v2_body.png')
print('saved')
