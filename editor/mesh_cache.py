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
            return doc, bufs
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
        return json.loads(js.decode("utf-8", "replace")), bins
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


def _collect_tris(doc, bufs, mesh_idxs, world_of):
    tris = []
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
                if "indices" in prim:
                    idx = _read_acc(doc, bufs, prim["indices"])
                    if not idx:
                        continue
                    idx = [int(v) for v in idx]
                else:
                    idx = list(range(len(pos)))
                mesh_node = world_of.get(mi)
                for t in range(0, len(idx) - 2, 3):
                    try:
                        tri = []
                        for k in idx[t:t + 3]:
                            v = pos[int(k)]
                            v = _mat_vec(mesh_node, (float(v[0]),
                                                     float(v[1]),
                                                     float(v[2])))
                            tri.append(v)
                        tris.append(tuple(tri))
                    except Exception:
                        continue
            except Exception:
                continue
    return tris


def load_mesh_tris(path, node="", max_tris=MAX_TRIS):
    """Normalized triangle soup for preview, or None.

    Triangles are centered and scaled so the longest bounding-box extent
    is 2.0 (half-extent 1.0). `node` selects a GLTF node subtree by name;
    empty means the whole file. Results (including None) are cached.
    """
    try:
        ap = os.path.abspath(path)
        key = (ap, os.path.getmtime(ap), node, int(max_tris))
    except OSError:
        return None
    if key in _cache:
        return _cache[key]
    tris = _parse(ap, node, max_tris)
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = tris
    return tris


def _parse(ap, node, max_tris):
    loaded = _load_doc(ap)
    if loaded is None:
        return None
    doc, bufs = loaded
    try:
        nodes = doc.get("nodes", [])
        meshes = doc.get("meshes", [])
        if not nodes or not meshes:
            return None
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
                return None
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

        tris = _collect_tris(doc, bufs, sorted(world_of), world_of)
        if not tris:
            return None
        if len(tris) > max_tris:
            step = len(tris) / max_tris
            tris = [tris[int(i * step)] for i in range(max_tris)]
        xs = [v[0] for t in tris for v in t]
        ys = [v[1] for t in tris for v in t]
        zs = [v[2] for t in tris for v in t]
        cx, cy, cz = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                      (min(zs) + max(zs)) / 2)
        ext = max(max(xs) - min(xs), max(ys) - min(ys),
                  max(zs) - min(zs), 1e-9)
        k = 2.0 / ext
        return [tuple((round((v[0] - cx) * k, 5), round((v[1] - cy) * k, 5),
                      round((v[2] - cz) * k, 5)) for v in t) for t in tris]
    except Exception:
        return None
