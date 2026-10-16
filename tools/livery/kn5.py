import struct, numpy as np
class R:
    def __init__(s, b): s.b, s.p = b, 0
    def i(s): v = struct.unpack_from('<i', s.b, s.p)[0]; s.p += 4; return v
    def f(s, n=1): v = struct.unpack_from('<%df' % n, s.b, s.p); s.p += 4 * n; return v
    def u8(s): v = s.b[s.p]; s.p += 1; return v
    def s(s_): n = s_.i(); v = s_.b[s_.p:s_.p + n].decode('latin1'); s_.p += n; return v
    def skip(s, n): s.p += n

def load(path):
    r = R(open(path, 'rb').read())
    assert r.b[:6] == b'sc6969'; r.p = 6
    ver = r.i()
    if ver > 5: r.i()
    tex = []
    for _ in range(r.i()):
        r.i(); name = r.s(); size = r.i(); r.skip(size); tex.append(name)
    mats = []
    for _ in range(r.i()):
        name = r.s(); shader = r.s(); r.u8(); r.u8(); r.i()
        for _ in range(r.i()): r.s(); r.skip(40)
        samp = {}
        for _ in range(r.i()):
            sn = r.s(); r.i(); samp[sn] = r.s()
        mats.append((name, shader, samp))
    meshes = []
    def node(parent):
        cls = r.i(); name = r.s(); nch = r.i(); r.u8()
        M = parent
        if cls == 1:
            m = np.array(r.f(16)).reshape(4, 4)
            M = m @ parent
        elif cls == 2:
            r.u8(); r.u8(); r.u8()
            nv = r.i()
            v = np.frombuffer(r.b, dtype='<f4', count=nv * 11, offset=r.p).reshape(nv, 11); r.skip(nv * 44)
            ni = r.i()
            idx = np.frombuffer(r.b, dtype='<u2', count=ni, offset=r.p).reshape(-1, 3); r.skip(ni * 2)
            mat = r.i(); r.i(); r.f(2); r.f(4); r.u8()
            meshes.append((name, v.copy(), idx.astype(np.int64), mat, parent.copy()))
        elif cls == 3:
            r.u8(); r.u8(); r.u8()
            for _ in range(r.i()): r.s(); r.skip(64)
            nv = r.i()
            v = np.frombuffer(r.b, dtype='<f4', count=nv * 19, offset=r.p).reshape(nv, 19); r.skip(nv * 76)
            ni = r.i()
            idx = np.frombuffer(r.b, dtype='<u2', count=ni, offset=r.p).reshape(-1, 3); r.skip(ni * 2)
            mat = r.i(); r.i(); r.f(2)
            meshes.append((name, v[:, :11].copy(), idx.astype(np.int64), mat, parent.copy()))
        else:
            raise ValueError('node class %d at %d' % (cls, r.p))
        for _ in range(nch): node(M)
    node(np.eye(4))
    return tex, mats, meshes
