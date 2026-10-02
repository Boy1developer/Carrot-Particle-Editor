# بنية تطبيق Carrot Particle Editor — كاملة

> محدّثة بعد التنظيم الاحترافي (مجلدات `editor/` `tests/` `tools/` `packaging/`).

## 1) شجرة الملفات (بدون `node_modules` / `dist` / `__pycache__`)

```
Carrot-Particle-Editor/
├── editor/
│   ├── studio_imgui.py             # الإديتور الرئيسي (Dear PyGui/ImGui + drawlist viewport)
│   └── particle_studio.py          # نسخة Tk الاحتياطية + طبقة اللوجيك المشتركة
├── tests/
│   ├── bootstrap.py                # إعداد sys.path (الجذر + editor/)
│   ├── test_imgui_nav.py           # نافيجيشن/سبلتر/تحويل النوع
│   ├── test_imgui_logic.py         # لوجيك المحاكاة + parity مع C++
│   ├── test_imgui_build.py         # بناء الواجهة كاملة headless
│   └── test_imgui_color.py         # ألوان per-state + ألوان المحرك
├── tools/
│   ├── rebuild_app.py              # أمر البناء الواحد: compile → C++ → PyInstaller → smoke → shortcut
│   └── make_icon.py                # توليد الأيقونات الشفافة من assets/download.png
├── packaging/
│   └── CarrotParticleEditor.spec   # وصفة الـ exe (مسارات مطلقة من جذر الريبو)
├── AdvancedParticleEmitter.json    # إكستنشن GDevelop (v1.0, type 2d/3d)
├── sample_effect.json              # مثال export جاهز
├── package.json / package-lock.json# اعتماديات المعاينة (three + pixi + typescript + esbuild)
├── particle_core.pyd/.lib/.pdb     # نواة C++ المبنية (غير ملتزمة — تُبنى عبر core/build_core.py)
├── Carrot Particle Editor.lnk      # شورتكت الويندوز (غير ملتزم — يُعاد توليده كل rebuild)
│
├── core/
│   ├── particle_core.cpp           # نواة المحاكاة C++ (مطابقة Python حرفيًا — 516 سطر)
│   ├── build_core.py               # بناء الـ .pyd: MSVC > g++ > clang++ > Zig (83 سطر)
│   ├── test_parity.py              # اختبار تطابق C++ مقابل Python (99/99)
│   └── test_behavior.py            # اختبار سلوك/أداء (~4ms @2000 particle)
│
├── render/
│   ├── __init__.py
│   ├── gl_view.py                  # ريندر GPU أوف‌سكرين: GLFW + ctypes OpenGL 3.3 + PPM (597 سطر)
│   ├── test_gl.py                  # اختبار تهيئة GL
│   ├── test_clip.py                # اختبار تطابق clip matrix مع StudioApp._proj
│   └── test_cost.py                # قياس تكلفة photo.configure (سبب dirty-region)
│
├── preview/
│   ├── preview.html                # قالب صفحة المعاينة (هيدر 🥕 Carrot Studio)
│   ├── preview.ts / preview.js     # محرك المعاينة + morph + zone/cone (452 سطر TS)
│   ├── main.ts / main.js           # منطق الصفحة: boot embed + semantic poll (219 سطر)
│   ├── three_scene.ts / .js        # طبقة WebGL ثلاثية الأبعاد مضيئة (282 سطر)
│   ├── pixi_scene.ts / .js         # طبقة WebGL ثنائية الأبعاد PixiJS (166 سطر)
│   ├── live_bundle.js              # الباندل المدمج (esbuild — 4903 سطر)
│   ├── live_effect.html            # صفحة مكتفية ذاتيًا 1.1MB (boot JSON، صفر fetch)
│   ├── last_effect.json            # آخر تأثير (poll حي من المعاينة)
│   ├── tsconfig.json
│   ├── test_engine.mjs / test_engine3d.mjs / test_guides.mjs
│   └── test_server.py
│
├── assets/
│   ├── app_icon.png                # أيقونة PNG (براند Carrot)
│   └── app_icon.ico                # أيقونة الـ exe والشورتكت
│
├── dist/
│   └── CarrotParticleEditor.exe    # المخرج المتجمد (windowed، بدون كونسول)
│
└── node_modules/                   # three + pixi.js + typescript + esbuild (للبناء فقط)
    ├── three/build/three.module.js  # ← يُضمَّن في الـ exe عبر spec datas
    └── pixi.js/dist/pixi.mjs        # ← يُضمَّن في الـ exe عبر spec datas
```

## 2) جدول الملفات: الدور + الحجم + السطور

### الجذر + المجلدات الجديدة

| المسار | الدور |
|---|---|
| `editor/studio_imgui.py` | الإديتور الرئيسي: Dear PyGui/ImGui + drawlist viewport + C++/Python sim + سيرفر المعاينة + تصدير JSON + undo/redo + Trails inspector المولّد من `TRAIL_SCHEMA` |
| `editor/trail_widgets.py` | ودجت المنحنيات/التدرجات القابلة لإعادة الاستخدام (drawlist + mouse handlers، حدث واحد عند الإفلات، LUT bake عند التغيير فقط) |
| `editor/trail_templates_ui.py` | متصفح قوالب الـ trails (Dear PyGui glue فقط): بطاقات 2-column + بحث/favs/recent + Apply بخطوة undo واحدة + حفظ/حذف بريسيتات المستخدم — كل الدمج/البحث/التحقق/LUTs/thumbnails في C++ |
| `editor/particle_studio.py` | نسخة Tk الاحتياطية + طبقة اللوجيك المشتركة (defaults/templates/validation/sim) + `TRAIL_SCHEMA` و `default_trails()` و `bake_curve/bake_gradient` + `app_base_dir()` لجذر الريبو |
| `tests/test_imgui_*.py` | اختبارات headless: nav/splitter/type-switch + logic/parity + build + color |
| `tests/test_trails_*.py` | اختبارات الـ trails: schema sync + roundtrip/heal + parity Python↔C++ (LUTs) + perf (300×32) + templates registry (27 تحميل/بحث/دمج/تحقق/thumbnails/حفظ-حذف) |
| `assets/presets/trails/*/*.json` | 27 قالب trails جاهز (combat 5 / magic 6 / movement 5 / nature 6 / stylized 5) — تُشحن مع الـ exe عبر `assets` datas |
| `tools/rebuild_app.py` | `python tools/rebuild_app.py` بعد أي تعديل: py_compile gate ← بناء C++ لو stale ← PyInstaller بالـ spec ← smoke boot 9 ثوانٍ ← توليد `.lnk` ← تنظيف `__pycache__` |
| `tools/make_icon.py` | توليد الأيقونات الشفافة من `assets/download.png` |
| `packaging/CarrotParticleEditor.spec` | datas: `preview` + `assets` + `render` + `three.module.js` + `pixi.mjs` + `glfw3.dll` — hiddenimports: `particle_core, render.gl_view, glfw` — أيقونة `assets/app_icon.ico` — `console=False` |
| `AdvancedParticleEmitter.json` | إكستنشن GDevelop كما هو — يدعم pyramid/torus + morph + تعبير Flow (مُصلَّح) |
| `sample_effect.json` | مثال export متوافق v1.0 |
| `sample_trail_effect.json` | مثال trails (width curve + color gradient + texture scroll، 3D additive) |
| `presets/trail_*.json` | بريسيتات الـ trails (Comet/Sword/Smoke/Beam/Neon/Rocket/Wand — ملفات effect عادية تُشحن مع الـ exe) |
| `assets/download.png` | الأرت الأصلي — مصدر `assets/app_icon.*` |
| `package.json` | `three@0.186 + pixi.js@8.21 + typescript@7 + esbuild@0.28` |
| `particle_core.pyd` | نواة C++ المبنية فعليًا (غير ملتزمة) |
| `particle_core.lib/.pdb` | مخلفات بناء MSVC (غير مطلوبة للتشغيل) |
| `Carrot Particle Editor.lnk` | شورتكت: Target=`dist\CarrotParticleEditor.exe` + Icon=`assets\app_icon.ico` (غير ملتزم) |

### `core/` — نواة المحاكاة

| الملف | الدور | سطور |
|---|---|---:|
| `particle_core.cpp` | `step()` يخرج `x,y,z,r,color,shape,depth + alpha,wx,wy` — نفس `SHAPE_ORDER` (12 شكل) ونفس semantics الـ morph + `TrailCfg` (parse إعدادات الـ trails و LUTs مطابقة Python حرفيًا) + registry القوالب (`trail_templates.h`: تحقق/دمج/بحث/favs/recents/thumbnails/textures/حفظ بريسيتات) | 1336 |
| `build_core.py` | ترتيب الكومبايلر: `cl > g++ > clang++ > Zig` (تثبيت تلقائي) — الخرج `particle_core.pyd` في جذر الريبو | 83 |
| `test_parity.py` | تطابق عددي Python↔C++ (99/99 ناجح) | 56 |
| `test_behavior.py` | سلوك + أداء (~4ms عند 2000 جسيم) | 96 |

### `render/` — الـ GPU داخل الإديتور

| الملف | الدور | سطور |
|---|---|---:|
| `gl_view.py` | سياق GLFW مخفي + OpenGL 3.3 بـ ctypes خام (بدون PyOpenGL/numpy — يعمل على Python 3.14) — خلفية+شبكة+جسيمات → بايتات PPM خام — `mat_clip_3d` تطابق `_proj` عدديًا — دعم `vp=(x0,y0,w2,h2)` للـ dirty-region | 597 |
| `test_gl.py` / `test_clip.py` / `test_cost.py` | تهيئة GL / تطابق المصفوفة (0/3000 parity) / إثبات أن `photo.configure` هو عنق الزجاجة (28ms كامل ← 6ms نصف) | 35/44/47 |

### `preview/` — معاينة المتصفح السريعة

| الملف | الدور | سطور |
|---|---|---:|
| `preview.html` | القالب المضمّن في الـ exe — هيدر `🥕 Carrot Studio` برتقالي + `boot-effect` | 64 |
| `preview.ts` | `ParticleEngine`: قيم birth→death (easing hyphenated) + shape flip عند raw≥0.5 + zone/cone | 452 |
| `main.ts` | boot JSON مدمج (بدون fetch) + poll دلالي لـ `last_effect.json` — مصدر واحد | 219 |
| `three_scene.ts` | طبقة 3D مضيئة (lights/shadows/guides) + تبديل mesh لكل state | 282 |
| `pixi_scene.ts` | طبقة 2D بـ PixiJS WebGL + `needShape` لكل state | 166 |
| `live_bundle.js` / `live_effect.html` | مخرجات esbuild المدمجة (1.1MB، صفر fetch — تتجاوز حجب localhost) | 4903/4969 |
| `last_effect.json` | الجسر الحي بين الإديتور والمعاينة (سطر واحد JSON) | 1 |
| `test_engine.mjs` / `test_engine3d.mjs` / `test_guides.mjs` / `test_server.py` | خضراء: المحرك + المشهد + الأدلة + السيرفر | — |

### `assets/` + `dist/`

| المسار | الدور |
|---|---|
| `assets/app_icon.png/.ico` | براند Carrot — أيقونة النافذة + الـ exe + الشورتكت |
| `dist/CarrotParticleEditor.exe` | التطبيق المتجمد (windowed) — يحمل كل تغيير بعد كل `tools/rebuild_app.py` |

## 3) ثوابت مشتركة (عقود بين المكونات)

- **سجل الجسيم:** `[x,y,vx,vy,age,c0,c1,s0,s1,life,z,vz,shape,tracks,dx,dy,dz,gx,gy,gz,sizeRatio,speedRatio]`
- **`SHAPE_ORDER` (12):** `circle, square, triangle, star, diamond, line, custom, sphere, cube, pyramid, torus, billboard` — مشترك Python↔C++
- **تنسيق التصدير:** JSON متوافق مع الإكستنشن v1.0 (`2d: needShape` / `3d: mesh swap`) — قيم easing بشرطة (`linear/ease-in/ease-out/ease-in-out`)
- **إحداثيات GL:** أحجام الشاشة تُفك مرة واحدة في vertex shader (ممنوع القسمة المسبقة في Python) — `mat_clip_3d == StudioApp._proj` عدديًا
- **ترتيب طبقات الكانفس:** خلفية ← شبكة ← صورة GPU (dirty subrect) ← أدلة/zone ← vignette (4 شرائط حافة) ← جيزمو (فوق الكل)
- **مسارات `_MEIPASS`:** الـ exe المجمد يقرأ `preview/` و`assets/` و`render/` وDLLs الـ glfw من داخل الحزمة
- **الموضع:** جيزمو الباعث للمعاينة فقط — الصادرات متمركزة على أوبجكت GDevelop

## 4) تدفق البيانات والبناء

```
core/particle_core.cpp --build_core.py--> particle_core.pyd --step()--> editor/particle_studio.py + editor/studio_imgui.py
                                                                              ├─ canvas (خلفية+شبكة tkinter)
                                                                              ├─ render/gl_view.py (GPU subrect → PPM → PhotoImage)
                                                                              ├─ preview/last_effect.json → live_effect.html (poll)
                                                                              └─ AdvancedParticleEmitter.json (export v1.0)
editor/ + preview/ + assets/ + render/ --tools/rebuild_app.py + packaging/.spec--> dist/CarrotParticleEditor.exe + .lnk
```

## 5) سير العمل المعتمد

1. عدّل أي ملف → 2. `python tools/rebuild_app.py` (إجباري — الـ exe والشورتكت يحملان كل تغيير) → 3. جرّب من الشورتكت → 4. للمعاينة: من داخل الإديتور (القالب مضمّن، لا كاش قديم).
