"""Bake, for every texel of body.dds, the 3D position and normal on the car."""
import numpy as np, kn5
S = 4096
tex, mats, meshes = kn5.load('car/gtp_radical_rxc_gt3.kn5')
body = {i for i, m in enumerate(mats) if any(t.lower() == 'body.dds' for t in m[2].values())}
pos = np.zeros((S, S, 3), np.float32); nrm = np.zeros((S, S, 3), np.float32)
mask = np.zeros((S, S), bool)
for name, v, idx, mat, M in meshes:
    if mat not in body: continue
    P = (np.c_[v[:, :3], np.ones(len(v))] @ M)[:, :3]
    N = v[:, 3:6] @ M[:3, :3]; N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
    U = v[:, 6] % 1.0 * S; V = v[:, 7] % 1.0 * S
    for a, b, c in idx:
        xs = np.array([U[a], U[b], U[c]]); ys = np.array([V[a], V[b], V[c]])
        if xs.max() - xs.min() > S / 2 or ys.max() - ys.min() > S / 2: continue  # wrapped
        x0, x1 = int(max(0, np.floor(xs.min()))), int(min(S - 1, np.ceil(xs.max())))
        y0, y1 = int(max(0, np.floor(ys.min()))), int(min(S - 1, np.ceil(ys.max())))
        det = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(det) < 1e-12: continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / det
        l1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / det
        l2 = 1 - l0 - l1
        e = -0.02  # a hair of dilation so seams don't show gaps
        m = (l0 >= e) & (l1 >= e) & (l2 >= e)
        if not m.any(): continue
        L = np.stack([l0, l1, l2], -1)[m]
        yy, xx = gy[m].astype(int), gx[m].astype(int)
        pos[yy, xx] = L @ P[[a, b, c]]
        nrm[yy, xx] = L @ N[[a, b, c]]
        mask[yy, xx] = True
np.savez_compressed('uvbake.npz', pos=pos.astype(np.float16), nrm=nrm.astype(np.float16), mask=mask)
p = pos[mask]
print('coverage %.1f%%' % (100 * mask.mean()), 'bbox min', p.min(0), 'max', p.max(0))
