# -*- coding: utf-8 -*-
"""Custom-model geometry for the 3D viewport preview (stdlib only).

Parses GLB/GLTF triangle meshes (positions + indices, node subtree with
transforms) and returns downsampled, normalized triangles that the ImGui
viewport projects per particle — so an uploaded model renders as itself
instead of a hollow placeholder box.

Never raises: any unreadable/unsupported file yields None (caller falls
back to the placeholder shape).
"""
import base64
import json
import os
import struct

MAX_TRIS = 150  # downsample cap per file cache entry
_MAX_BYTES = 200 * 1024 * 1024  # refuse absurd files

_COMP = {  # componentType -> (struct fmt, size)
    5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
    5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4),
}
_TYPE_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

_cache = {}
_CACHE_MAX = 8


def _load_doc(path):
    """-> (doc, buffers) or None. buffers[i] = bytes or None."""
    try:
        if os.path.getsize(path) > _MAX_BYTES:
            return None
    except OSError:
        return None
    try:
        if path.lower().endswith(".gltf"):
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            base = os.path.dirname(os.path.abspath(path))
            bufs = []
            for b in doc.get("buffers", []):
                uri = b.get("uri") or ""
                if uri.startswith("data:"):
                    try:
                        bufs.append(base64.b64decode(uri.split(",", 1)[1]))
                    except Exception:
                        bufs.append(None)
                elif uri:
                    p = os.path.normpath(os.path.join(base, uri))
                    try:
                        with open(p, "rb") as f:
                            bufs.append(f.read())
                    except OSError:
                        bufs.append(None)
                else:
                    bufs.append(None)
            return doc, bufs, base
        with open(path, "rb") as f:
            data = f.read()
        if len(data) < 12 or data[:4] != b"glTF":
            return None
        off, bins, js = 12, [], None
        while off + 8 <= len(data):
            clen, ctype = struct.unpack("<II", data[off:off + 8])
            chunk = data[off + 8:off + 8 + clen]
            if ctype == 0x4E4F534A:  # 'JSON'
                js = chunk
            elif ctype == 0x004E4942:  # 'BIN\0'
                bins.append(bytes(chunk))
            off += 8 + clen
        if js is None:
            return None
        return json.loads(js.decode("utf-8", "replace")), bins, None
    except Exception:
        return None


def _read_acc(doc, bufs, idx):
    """-> list of tuples or None."""
    try:
        acc = doc["accessors"][idx]
        fmt, sz = _COMP[acc["componentType"]]
        n_comp = _TYPE_N[acc["type"]]
        count = int(acc["count"])
        if count <= 0 or count > 10_000_000:
            return None
        bv = doc["bufferViews"][acc["bufferView"]]
        raw = bufs[bv["buffer"]]
        if raw is None:
            return None
        base = int(bv.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
        stride = int(bv.get("byteStride", 0)) or n_comp * sz
        item = n_comp * sz
        if stride < item:
            return None
        out = []
        for i in range(count):
            off = base + i * stride
            vals = struct.unpack("<" + fmt * n_comp, raw[off:off + item])
            out.append(vals if n_comp > 1 else vals[0])
            if off + item > len(raw):
                return None
        return out
    except Exception:
        return None


def _mat_mult(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4))
             for j in range(4)] for i in range(4)]


def _mat_vec(m, v):
    x, y, z = v
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def _node_local(node):
    if isinstance(node.get("matrix"), list) and len(node["matrix"]) == 16:
        c = [float(v) for v in node["matrix"]]  # glTF: column-major
        return [[c[j * 4 + i] for j in range(4)] for i in range(4)]
    t = [float(v) for v in node.get("translation", (0.0, 0.0, 0.0))]
    r = [float(v) for v in node.get("rotation", (0.0, 0.0, 0.0, 1.0))]
    s = [float(v) for v in node.get("scale", (1.0, 1.0, 1.0))]
    x, y, z, w = r
    m = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[m[i][j] * s[j] for j in range(3)] + [t[i]] for i in range(3)
            ] + [[0.0, 0.0, 0.0, 1.0]]


def _image_bytes(doc, bufs, base, img):
    """Raw bytes of a glTF image dict (bufferView / data-uri / file)."""
    try:
        if "bufferView" in img:
            bv = doc["bufferViews"][img["bufferView"]]
            raw = bufs[bv["buffer"]]
            if raw is None:
                return None
            off = int(bv.get("byteOffset", 0))
            ln = int(bv.get("byteLength", len(raw) - off))
            return raw[off:off + ln]
        uri = img.get("uri") or ""
        if uri.startswith("data:"):
            return base64.b64decode(uri.split(",", 1)[1])
        if uri and base:
            p = os.path.normpath(os.path.join(base, uri))
            with open(p, "rb") as f:
                return f.read()
        return None
    except Exception:
        return None


def _mat_of(doc, bufs, base, prim):
    """-> ((fr,fg,fb) factor 0-1, decoded image or None, cullable bool)."""
    factor, img, cull = (1.0, 1.0, 1.0), None, True
    try:
        mats = doc.get("materials", [])
        m = mats[int(prim.get("material", -1))]
        cull = not bool(m.get("doubleSided", False))
        pbr = m.get("pbrMetallicRoughness", {})
        fc = pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
        factor = (float(fc[0]), float(fc[1]), float(fc[2]))
        tex = pbr.get("baseColorTexture")
        if isinstance(tex, dict):
            tx = doc.get("textures", [])[int(tex.get("index", -1))]
            src = tx.get("source")
            images = doc.get("images", [])
            if src is not None and 0 <= int(src) < len(images):
                im = images[int(src)]
                hint = ""
                mt = str(im.get("mimeType", ""))
                if "png" in mt:
                    hint = "png"
                data = _image_bytes(doc, bufs, base, im)
                if data:
                    img = _decode_image(data, hint)
    except Exception:
        pass
    return factor, img, cull


def _collect_tris(doc, bufs, base, mesh_idxs, world_of):
    """-> list of (tri, (u, v, factor, img, cull)) keeping data paired."""
    out = []
    for mi in mesh_idxs:
        try:
            mesh = doc["meshes"][mi]
        except Exception:
            continue
        for prim in mesh.get("primitives", []):
            try:
                if int(prim.get("mode", 4)) != 4:  # triangles only
                    continue
                pos = _read_acc(doc, bufs, prim["attributes"]["POSITION"])
                if not pos:
                    continue
                uv_acc = (prim.get("attributes", {}).get("TEXCOORD_0"))
                uvs = _read_acc(doc, bufs, uv_acc) if uv_acc is not None \
                    else None
                factor, img, cull = _mat_of(doc, bufs, base, prim)
                if "indices" in prim:
                    idx = _read_acc(doc, bufs, prim["indices"])
                    if not idx:
                        continue
                    idx = [int(v) for v in idx]
                else:
                    idx = list(range(len(pos)))
                mesh_node = world_of.get(mi)
                nuv = len(uvs) if uvs else 0
                for t in range(0, len(idx) - 2, 3):
                    try:
                        tri, uvt = [], []
                        for n, k in enumerate(idx[t:t + 3]):
                            v = pos[int(k)]
                            v = _mat_vec(mesh_node, (float(v[0]),
                                                     float(v[1]),
                                                     float(v[2])))
                            tri.append(v)
                            if uvs and int(k) < nuv:
                                uv = uvs[int(k)]
                                uvt.append((float(uv[0]), float(uv[1])))
                        uu = sum(u for u, _ in uvt) / len(uvt) if uvt \
                            else 0.5
                        vv = sum(v for _, v in uvt) / len(uvt) if uvt \
                            else 0.5
                        out.append((tuple(tri), (uu, vv, factor, img,
                                                 cull)))
                    except Exception:
                        continue
            except Exception:
                continue
    return out


def _decode_png(data):
    """Minimal stdlib PNG decoder -> (w, h, [r,g,b]*w*h) or None.

    8-bit non-interlaced only (covers virtually all glTF textures);
    color types 0/2/3/4/6. Anything fancier returns None.
    """
    try:
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        off, w, h, depth, ctype, comp, filt, inter = 0, 0, 0, 0, 0, 0, 0, 0
        plte, trns, raws = None, None, []
        off = 8
        import zlib
        while off + 8 <= len(data):
            ln = struct.unpack(">I", data[off:off + 4])[0]
            typ = data[off + 4:off + 8]
            chunk = data[off + 8:off + 8 + ln]
            if typ == b"IHDR":
                w, h, depth, ctype, comp, filt, inter = \
                    struct.unpack(">IIBBBBB", chunk)
            elif typ == b"PLTE":
                plte = chunk
            elif typ == b"tRNS":
                trns = chunk
            elif typ == b"IDAT":
                raws.append(chunk)
            elif typ == b"IEND":
                break
            off += 12 + ln
        if depth != 8 or inter != 0 or ctype not in (0, 2, 3, 4, 6):
            return None
        ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
        raw = zlib.decompress(b"".join(raws))
        stride, px = w * ch, []
        pos = 0
        prev = bytearray(stride)
        for _ in range(h):
            f = raw[pos]
            pos += 1
            cur = bytearray(raw[pos:pos + stride])
            pos += stride
            if f == 1:
                for i in range(ch, stride):
                    cur[i] = (cur[i] + cur[i - ch]) & 255
            elif f == 2:
                for i in range(stride):
                    cur[i] = (cur[i] + prev[i]) & 255
            elif f == 3:
                for i in range(stride):
                    a = cur[i - ch] if i >= ch else 0
                    cur[i] = (cur[i] + ((a + prev[i]) >> 1)) & 255
            elif f == 4:
                for i in range(stride):
                    a = cur[i - ch] if i >= ch else 0
                    b = prev[i]
                    c = prev[i - ch] if i >= ch else 0
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pr = a if (pa <= pb and pa <= pc) else \
                        (b if pb <= pc else c)
                    cur[i] = (cur[i] + pr) & 255
            elif f != 0:
                return None
            px.append(bytes(cur))
            prev = cur
        out = []
        for row in px:
            for x in range(w):
                o = x * ch
                if ctype == 0:
                    out += [row[o]] * 3
                elif ctype == 2:
                    out += [row[o], row[o + 1], row[o + 2]]
                elif ctype == 3:
                    if plte is None or o >= len(plte) // 3 * 3:
                        return None
                    out += [plte[o * 3], plte[o * 3 + 1], plte[o * 3 + 2]]
                elif ctype == 4:
                    out += [row[o]] * 3
                else:
                    out += [row[o], row[o + 1], row[o + 2]]
        return w, h, out
    except Exception:
        return None


def _decode_image(data, hint=""):
    """-> (w, h, flat [r,g,b]) or None. PIL first, stdlib PNG fallback."""
    if not data:
        return None
    try:
        from PIL import Image as _Im
        try:
            im = _Im.open(__import__("io").BytesIO(bytes(data)))
            im = im.convert("RGB")
            w, h = im.size
            flat = []
            for p in im.getdata():
                flat += [p[0], p[1], p[2]]
            return w, h, flat
        except Exception:
            pass
    except Exception:
        pass
    if hint == "png" or (bytes(data[:4]).startswith(b"\x89PNG")):
        return _decode_png(bytes(data))
    return None


def _sample(img, u, v):
    """Nearest texel, v-flipped to GL convention. img=(w,h,flat)."""
    try:
        w, h, flat = img
        x = min(w - 1, max(0, int(u * w)))
        y = min(h - 1, max(0, int((1.0 - v) * h)))
        o = (y * w + x) * 3
        return flat[o], flat[o + 1], flat[o + 2]
    except Exception:
        return 255, 255, 255


def _normalize(pairs, max_tris):
    """Downsample + center/scale geometry, keeping material data paired."""
    if not pairs:
        return None
    if len(pairs) > max_tris:
        step = len(pairs) / max_tris
        pairs = [pairs[int(i * step)] for i in range(max_tris)]
    xs = [v[0] for t, _ in pairs for v in t]
    ys = [v[1] for t, _ in pairs for v in t]
    zs = [v[2] for t, _ in pairs for v in t]
    cx, cy, cz = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                  (min(zs) + max(zs)) / 2)
    ext = max(max(xs) - min(xs), max(ys) - min(ys),
              max(zs) - min(zs), 1e-9)
    k = 2.0 / ext
    return [((tuple((round((v[0] - cx) * k, 5), round((v[1] - cy) * k, 5),
                    round((v[2] - cz) * k, 5)) for v in t)), m)
            for t, m in pairs]


def _parse_obj(ap):
    verts, tris = [], []
    try:
        with open(ap, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("v "):
                    try:
                        p = line.split()
                        verts.append((float(p[1]), float(p[2]),
                                      float(p[3])))
                    except Exception:
                        continue
                elif line.startswith("f "):
                    try:
                        idx = []
                        for tok in line.split()[1:]:
                            vi = int(tok.split("/")[0])
                            idx.append(vi - 1 if vi > 0 else
                                       len(verts) + vi)
                        pts = [verts[i] for i in idx]
                        for k in range(1, len(pts) - 1):
                            tris.append((pts[0], pts[k], pts[k + 1]))
                    except Exception:
                        continue
    except OSError:
        return None
    return tris or None


def load_mesh(path, node="", max_tris=MAX_TRIS):
    """(normalized tris, per-tri (r,g,b), per-tri cullable) or Nones.

    Material color = texture texel at the triangle UV centroid times the
    baseColorFactor (white when untextured). cullable is False for
    doubleSided materials (both faces drawn). Same cache as load_mesh_tris.
    """
    try:
        ap = os.path.abspath(path)
        key = (ap, os.path.getmtime(ap), node, int(max_tris))
    except OSError:
        return None, None, None
    if key in _cache:
        return _cache[key]
    if ap.lower().endswith(".obj"):
        pairs = _normalize([(t, (0.5, 0.5, (1.0, 1.0, 1.0), None, True))
                            for t in (_parse_obj(ap) or [])], max_tris)
        result = ([t for t, _ in pairs],
                  [(255, 255, 255)] * len(pairs),
                  [True] * len(pairs)) if pairs else (None, None, None)
    else:
        result = _parse(ap, node, max_tris)
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = result
    return result


def load_mesh_tris(path, node="", max_tris=MAX_TRIS):
    """Normalized triangle soup for preview, or None (see load_mesh)."""
    tris, _tex, _cull = load_mesh(path, node, max_tris)
    return tris


def _parse(ap, node, max_tris):
    loaded = _load_doc(ap)
    if loaded is None:
        return None, None, None
    doc, bufs, base = loaded
    try:
        nodes = doc.get("nodes", [])
        meshes = doc.get("meshes", [])
        if not nodes or not meshes:
            return None, None, None
        parent = {}
        for ni, nd in enumerate(nodes):
            for ch in nd.get("children", []):
                try:
                    parent[int(ch)] = ni
                except Exception:
                    pass

        def subtree_meshes(root):
            out, stack = [], [root]
            while stack:
                cur = stack.pop()
                try:
                    nd = nodes[cur]
                except Exception:
                    continue
                m = nd.get("mesh")
                if m is not None:
                    try:
                        out.append(int(m))
                    except Exception:
                        pass
                stack.extend(int(c) for c in nd.get("children", [])
                             if isinstance(c, int))
            return out

        targets = []
        if node:
            for ni, nd in enumerate(nodes):
                if str(nd.get("name", "")) == node:
                    targets.append(ni)
            if not targets:
                return None, None, None
        else:
            targets = list(range(len(nodes)))

        world_of = {}  # mesh idx -> world matrix
        for root in targets:
            chain, cur = [], root
            while True:
                try:
                    chain.append(nodes[cur])
                except Exception:
                    break
                cur = parent.get(cur)
                if cur is None:
                    break
            mat = [[1.0 if i == j else 0.0 for j in range(4)]
                   for i in range(4)]
            for nd in reversed(chain):
                try:
                    mat = _mat_mult(mat, _node_local(nd))
                except Exception:
                    pass
            for mi in subtree_meshes(root):
                world_of.setdefault(mi, mat)

        pairs = _normalize(_collect_tris(doc, bufs, base,
                                           sorted(world_of), world_of),
                           max_tris)
        if not pairs:
            return None, None, None
        tris, texels, culls = [], [], []
        for t, (u, v, factor, img, cull) in pairs:
            tris.append(t)
            culls.append(bool(cull))
            if img is not None:
                pr, pg, pb = _sample(img, u, v)
            else:
                pr, pg, pb = 255, 255, 255
            fr, fg, fb = factor
            texels.append((max(0, min(255, int(round(pr * fr)))),
                           max(0, min(255, int(round(pg * fg)))),
                           max(0, min(255, int(round(pb * fb))))))
        return tris, texels, culls
    except Exception:
        return None, None, None
