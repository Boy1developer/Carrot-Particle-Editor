/**
 * Three.js WebGL layer for the ParticleFX fast preview (3D mode).
 * - Reuses the ParticleEngine simulation + keyframe morph sampling
 * - Real 3D meshes per shape (InstancedMesh, additive blending)
 * - Lit solids (hemisphere + shadowed directional), shadow-catcher floor,
 *   ACES tone mapping, fog, emission-zone + cone guides
 * - Orbit camera driven by engine.cam (drag/wheel handled in preview.html)
 */
import * as THREE from "three";
const CAP = 4000; // per-shape instance cap (matches engine MAX_POOL)
const BASE_DIST = 560;
function starShape2D(outer, inner) {
    const s = new THREE.Shape();
    for (let k = 0; k < 10; k++) {
        const a = (k / 10) * Math.PI * 2 - Math.PI / 2;
        const r = (k % 2 === 0) ? outer : inner;
        const x = Math.cos(a) * r, y = Math.sin(a) * r;
        if (k === 0)
            s.moveTo(x, y);
        else
            s.lineTo(x, y);
    }
    s.closePath();
    return s;
}
function triangleShape2D(r) {
    const s = new THREE.Shape();
    for (let k = 0; k < 3; k++) {
        const a = (k / 3) * Math.PI * 2 - Math.PI / 2;
        const x = Math.cos(a) * r, y = Math.sin(a) * r;
        if (k === 0)
            s.moveTo(x, y);
        else
            s.lineTo(x, y);
    }
    s.closePath();
    return s;
}
function circleLine(r, axis, seg = 48) {
    const pts = [];
    for (let k = 0; k <= seg; k++) {
        const a = (k / seg) * Math.PI * 2;
        const c = Math.cos(a) * r, s = Math.sin(a) * r;
        pts.push(axis === "xy" ? new THREE.Vector3(c, s, 0)
            : axis === "xz" ? new THREE.Vector3(c, 0, s)
                : new THREE.Vector3(0, c, s));
    }
    return new THREE.BufferGeometry().setFromPoints(pts);
}
export class ThreeScene {
    constructor(canvas, engine) {
        this.canvas = canvas;
        this.engine = engine;
        this.scene = new THREE.Scene();
        this.meshes = [];
        this.byShape = {};
        this.solid = [];
        this.guides = new THREE.Group();
        this.guideRev = -1;
        this.dummy = new THREE.Object3D();
        this.tmpColor = new THREE.Color();
        this.lastW = 0;
        this.lastH = 0;
        // flat shapes billboard toward the camera; solids tumble slowly with age
        this.flat = new Set(["square", "billboard", "triangle", "star", "line", "circle", "custom"]);
        this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
        this.renderer.setClearColor(0x000000, 0); // CSS gradient shows through
        this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.1;
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.camera = new THREE.PerspectiveCamera(60, 1, 1, 6000);
        this.scene.fog = new THREE.Fog(0x101218, 900, 2400);
        // lighting rig: cool sky / warm ground + shadowed key light
        this.scene.add(new THREE.HemisphereLight(0x8fb4ff, 0x2a1a10, 0.85));
        const key = new THREE.DirectionalLight(0xfff2e0, 2.4);
        key.position.set(180, 260, 120);
        key.castShadow = true;
        key.shadow.mapSize.set(1024, 1024);
        key.shadow.camera.left = -320;
        key.shadow.camera.right = 320;
        key.shadow.camera.top = 320;
        key.shadow.camera.bottom = -320;
        key.shadow.camera.far = 1200;
        key.shadow.bias = -0.002;
        this.scene.add(key);
        const rim = new THREE.DirectionalLight(0x4d9fff, 0.7);
        rim.position.set(-220, 120, -180);
        this.scene.add(rim);
        // shadow-catcher floor + grid + axes + emitter dot
        const floor = new THREE.Mesh(new THREE.PlaneGeometry(1400, 1400), new THREE.ShadowMaterial({ opacity: 0.35 }));
        floor.rotation.x = -Math.PI / 2;
        floor.position.y = -0.5;
        floor.receiveShadow = true;
        this.scene.add(floor);
        const grid = new THREE.GridHelper(520, 10, 0x3a3d55, 0x2c2e44);
        this.scene.add(grid);
        this.scene.add(new THREE.AxesHelper(70));
        const dot = new THREE.Mesh(new THREE.SphereGeometry(4, 12, 10), new THREE.MeshBasicMaterial({ color: 0xffffff }));
        this.scene.add(dot);
        this.scene.add(this.guides);
        const geos = {
            sphere: new THREE.SphereGeometry(0.9, 14, 10),
            cube: new THREE.BoxGeometry(1.4, 1.4, 1.4),
            pyramid: new THREE.ConeGeometry(0.95, 1.7, 4),
            torus: new THREE.TorusGeometry(0.65, 0.30, 10, 20),
            diamond: new THREE.OctahedronGeometry(1.0),
            square: new THREE.PlaneGeometry(1.8, 1.8),
            billboard: new THREE.PlaneGeometry(1.8, 1.8),
            triangle: new THREE.ShapeGeometry(triangleShape2D(1.15)),
            star: new THREE.ShapeGeometry(starShape2D(1.15, 0.52)),
            line: new THREE.PlaneGeometry(3.4, 0.5),
            circle: new THREE.CircleGeometry(1.0, 28),
            custom: new THREE.PlaneGeometry(1.8, 1.8),
        };
        geos["pyramid"].rotateY(Math.PI / 4);
        const order = ["sphere", "cube", "pyramid", "torus", "diamond",
            "square", "billboard", "triangle", "star", "line", "circle", "custom"];
        order.forEach((key, idx) => {
            const isSolid = !this.flat.has(key);
            const mat = isSolid
                ? new THREE.MeshStandardMaterial({
                    roughness: 0.38, metalness: 0.05,
                    transparent: true, opacity: 1,
                    blending: THREE.AdditiveBlending, depthWrite: false,
                })
                : new THREE.MeshBasicMaterial({
                    transparent: true, opacity: 1,
                    blending: THREE.AdditiveBlending, depthWrite: false,
                    side: THREE.DoubleSide,
                });
            const m = new THREE.InstancedMesh(geos[key], mat, CAP);
            m.frustumCulled = false;
            m.castShadow = isSolid;
            m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
            const black = new THREE.Color(0, 0, 0);
            for (let i = 0; i < CAP; i++) {
                this.dummy.position.set(0, 0, 0);
                this.dummy.scale.set(0.0001, 0.0001, 0.0001);
                this.dummy.updateMatrix();
                m.setMatrixAt(i, this.dummy.matrix);
                m.setColorAt(i, black);
            }
            m.count = 0;
            this.scene.add(m);
            this.meshes.push(m);
            this.solid.push(isSolid);
            this.byShape[key] = idx;
        });
    }
    normShape(shape) {
        const s = String(shape ?? "sphere").toLowerCase();
        if (s === "billboard")
            return "billboard";
        return Object.prototype.hasOwnProperty.call(this.byShape, s) ? s : "sphere";
    }
    /** Rebuild zone + cone wireframes when a new effect is loaded. */
    rebuildGuides() {
        while (this.guides.children.length) {
            const c = this.guides.children.pop();
            if (!c)
                break;
            this.guides.remove(c);
            c.traverse((o) => {
                const anyObj = o;
                if (anyObj.geometry)
                    anyObj.geometry.dispose();
                const mats = Array.isArray(anyObj.material)
                    ? anyObj.material : anyObj.material ? [anyObj.material] : [];
                for (const mm of mats)
                    mm.dispose();
            });
        }
        const mat = (color) => new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.75 });
        const z = this.engine.zoneInfo();
        const zmat = mat(0x4d9fff);
        if (z.shape === "sphere" || z.shape === "circle") {
            const r = Math.max(1, z.radius);
            for (const ax of ["xy", "xz", "yz"])
                this.guides.add(new THREE.Line(circleLine(r, ax), zmat));
        }
        else if (z.shape === "box" || z.shape === "rectangle") {
            const g = new THREE.BoxGeometry(Math.max(1, z.width), Math.max(1, z.height), Math.max(1, z.depth));
            const e = new THREE.LineSegments(new THREE.EdgesGeometry(g), zmat);
            e.rotation.y = (z.rot || 0) * Math.PI / 180;
            this.guides.add(e);
            g.dispose();
        }
        else if (z.shape === "line") {
            const half = Math.max(1, z.length) / 2;
            const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-half, 0, 0), new THREE.Vector3(half, 0, 0)]);
            const l = new THREE.Line(g, zmat);
            l.rotation.y = (z.rot || 0) * Math.PI / 180;
            this.guides.add(l);
        }
        const cn = this.engine.coneInfo();
        if (cn.spread < 360) {
            const cmat = mat(0xe8d44d);
            const az = cn.direction * Math.PI / 180;
            const el = cn.directionY * Math.PI / 180;
            const bx = Math.cos(el) * Math.cos(az);
            const by = Math.sin(el);
            const bz = Math.cos(el) * Math.sin(az);
            const L = 110;
            const off = Math.tan((cn.spread / 2) * Math.PI / 180);
            // orthonormal basis around the base direction
            let ux = 0, uy = 1, uz = 0;
            if (Math.abs(by) > 0.95) {
                ux = 1;
                uy = 0;
            }
            let ex = by * uz - bz * uy, ey = bz * ux - bx * uz, ez = bx * uy - by * ux;
            const n = Math.hypot(ex, ey, ez) || 1;
            ex /= n;
            ey /= n;
            ez /= n;
            const pts = [];
            for (const sgn of [1, -1]) {
                let dx = bx + ex * off * sgn, dy = by + ey * off * sgn, dz = bz + ez * off * sgn;
                const m = Math.hypot(dx, dy, dz) || 1;
                dx /= m;
                dy /= m;
                dz /= m;
                pts.push(new THREE.Vector3(0, 0, 0), new THREE.Vector3(dx * L, dy * L, dz * L));
            }
            // rim arc across the two edge rays
            const rimPts = [];
            for (let k = 0; k <= 24; k++) {
                const t = k / 24 - 0.5; // -0.5..0.5 across
                const ang = Math.atan(off) * t * 2;
                const ca = Math.cos(ang), sa = Math.sin(ang);
                rimPts.push(new THREE.Vector3((bx * ca + ex * sa) * L, (by * ca + ey * sa) * L, (bz * ca + ez * sa) * L));
            }
            const cg = new THREE.BufferGeometry().setFromPoints(pts.concat(rimPts));
            this.guides.add(new THREE.LineSegments(cg, cmat));
        }
    }
    render() {
        const W = Math.max(1, Math.round(this.canvas.clientWidth || 1));
        const H = Math.max(1, Math.round(this.canvas.clientHeight || 1));
        if (W !== this.lastW || H !== this.lastH) {
            this.lastW = W;
            this.lastH = H;
            this.renderer.setSize(W, H, false);
            this.camera.aspect = W / H;
            this.camera.updateProjectionMatrix();
        }
        if (this.guideRev !== this.engine.effectVersion) {
            this.guideRev = this.engine.effectVersion;
            this.rebuildGuides();
        }
        // orbit camera from the shared engine.cam state
        const cam = this.engine.cam;
        const d = BASE_DIST / Math.max(0.3, cam.zoom);
        const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
        this.camera.position.set(d * cp * Math.sin(cam.yaw), d * sp, d * cp * Math.cos(cam.yaw));
        this.camera.lookAt(0, 0, 0);
        const counts = new Array(this.meshes.length).fill(0);
        const n = this.engine.activeCount;
        for (let i = 0; i < n; i++) {
            const st = this.engine.particleState(i);
            const sm = this.engine.sampleAt(st.age, i);
            const key = this.normShape(sm.shape);
            const mi = this.byShape[key];
            const slot = counts[mi]++;
            if (slot >= CAP)
                continue;
            const s = Math.max(0.01, sm.size);
            this.dummy.position.set(st.x, st.y, st.z);
            if (this.flat.has(key)) {
                this.dummy.quaternion.copy(this.camera.quaternion);
            }
            else {
                this.dummy.rotation.set(st.age * 0.7, st.age * 0.9, 0);
            }
            this.dummy.scale.set(s, s, s);
            this.dummy.updateMatrix();
            this.meshes[mi].setMatrixAt(slot, this.dummy.matrix);
            // additive blending: bake alpha into RGB (matches 2D preview look)
            this.tmpColor.setRGB((sm.r / 255) * sm.a, (sm.g / 255) * sm.a, (sm.b / 255) * sm.a);
            this.meshes[mi].setColorAt(slot, this.tmpColor);
        }
        for (let m = 0; m < this.meshes.length; m++) {
            this.meshes[m].count = counts[m];
            this.meshes[m].instanceMatrix.needsUpdate = true;
            const ic = this.meshes[m].instanceColor;
            if (ic)
                ic.needsUpdate = true;
        }
        this.renderer.render(this.scene, this.camera);
    }
}
