"""PNG -> DXT5 DDS with a full mipmap chain (Pillow writes one level only)."""
import io, struct, sys
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert('RGBA')
levels, cur = [], im
while True:
    buf = io.BytesIO(); cur.save(buf, format='DDS', pixel_format='DXT5')
    data = buf.getvalue()
    assert data[84:88] == b'DXT5', data[84:88]
    levels.append(data)
    if cur.width == 1 and cur.height == 1: break
    cur = cur.resize((max(1, cur.width // 2), max(1, cur.height // 2)), Image.LANCZOS)
head = bytearray(levels[0][:128])
flags = struct.unpack_from('<I', head, 8)[0] | 0x20000          # DDSD_MIPMAPCOUNT
struct.pack_into('<I', head, 8, flags)
struct.pack_into('<I', head, 28, len(levels))
caps = struct.unpack_from('<I', head, 108)[0] | 0x8 | 0x400000  # COMPLEX | MIPMAP
struct.pack_into('<I', head, 108, caps)
with open(dst, 'wb') as f:
    f.write(head)
    for d in levels: f.write(d[128:])
print(dst, len(levels), 'levels')
