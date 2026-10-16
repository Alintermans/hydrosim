import sys, numpy as np, kn5
from PIL import Image
tex_path = sys.argv[1]; out = sys.argv[2]
tex, mats, meshes = kn5.load('car/gtp_radical_rxc_gt3.kn5')
body = {i for i, m in enumerate(mats) if any(t.lower() == 'body.dds' for t in m[2].values())}
P, N, UV, F = [], [], [], []
off = 0
for name, v, idx, mat, M in meshes:
    if mat not in body: continue
    pos = np.c_[v[:, :3], np.ones(len(v))] @ M
    nrm = v[:, 3:6] @ M[:3, :3]
    P.append(pos[:, :3]); N.append(nrm); UV.append(v[:, 6:8]); F.append(idx + off); off += len(v)
P, N, UV, F = map(np.concatenate, (P, N, UV, F))
N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
T = np.asarray(Image.open(tex_path).convert('RGB').resize((2048, 2048)), dtype=np.float32) / 255

def rot(yaw, pitch):
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    Ry = np.array([[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cp, sp], [0, -sp, cp]])
    return Ry @ Rx

def view(yaw, pitch, W=900, H=520):
    R = rot(np.radians(yaw), np.radians(pitch))
    p = P @ R; n = N @ R
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    s = 0.9 * min(W / (x.max() - x.min()), H / (y.max() - y.min()))
    sx = (x - (x.max() + x.min()) / 2) * s + W / 2
    sy = H / 2 - (y - (y.max() + y.min()) / 2) * s
    img = np.zeros((H, W, 3), np.float32) + 0.12
    zb = np.full((H, W), 1e9)
    light = np.array([0.3, 0.8, 0.5]); light /= np.linalg.norm(light)
    for a, b, c in F:
        xs = np.array([sx[a], sx[b], sx[c]]); ys = np.array([sy[a], sy[b], sy[c]])
        x0, x1 = int(max(0, xs.min())), int(min(W - 1, xs.max()) + 1)
        y0, y1 = int(max(0, ys.min())), int(min(H - 1, ys.max()) + 1)
        if x1 <= x0 or y1 <= y0: continue
        det = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(det) < 1e-9: continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        l0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / det
        l1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / det
        l2 = 1 - l0 - l1
        m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not m.any(): continue
        zz = l0 * z[a] + l1 * z[b] + l2 * z[c]
        sub = zb[y0:y1, x0:x1]
        m &= zz < sub
        if not m.any(): continue
        u = l0 * UV[a, 0] + l1 * UV[b, 0] + l2 * UV[c, 0]
        vv = l0 * UV[a, 1] + l1 * UV[b, 1] + l2 * UV[c, 1]
        col = T[(np.clip(vv % 1, 0, 0.9999) * 2048).astype(int), (np.clip(u % 1, 0, 0.9999) * 2048).astype(int)]
        nn = l0[..., None] * n[a] + l1[..., None] * n[b] + l2[..., None] * n[c]
        nn /= np.linalg.norm(nn, axis=-1, keepdims=True) + 1e-9
        sh = 0.55 + 0.45 * np.abs(nn @ (light @ R))
        sub[m] = zz[m]
        img[y0:y1, x0:x1][m] = col[m] * sh[m][:, None]
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).transpose(Image.FLIP_LEFT_RIGHT)  # AC is left-handed

import os
vs = os.environ.get('VIEWS')
views = [view(*map(float, v.split(':'))) for v in vs.split(',')] if vs else [view(90, 0), view(-90, 0), view(35, -18), view(215, -18), view(180, -12), view(0, -12)]
sheet = Image.new('RGB', (1800, 1560))
for i, im in enumerate(views): sheet.paste(im, ((i % 2) * 900, (i // 2) * 520))
sheet.save(out, quality=88)
print('rendered')
