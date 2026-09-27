# بنية تطبيق Carrot Particle Editor — كاملة

> مولّد آليًا من فحص الملفات على القرص بتاريخ 2026-09-27.
> الجذر: `C:\Users\pc\Downloads\partical system` (ليس git repo — كل التعديلات ملفات محلية غير ملتزمة).

## 1) شجرة الملفات (بدون `node_modules` / `dist` / `__pycache__`)

```
partical system/
├── particle_studio.py              # التطبيق كله: UI + محاكاة + GPU + سيرفر المعاينة (2683 سطر)
├── rebuild_app.py                  # أمر البناء الواحد: compile → C++ → PyInstaller → smoke → shortcut (71 سطر)
├── CarrotParticleEditor.spec       # وصفة الـ exe: أيقونة + datas + hiddenimports (47 سطر)
├── AdvancedParticleEmitter.json    # إكستنشن GDevelop (v1.0, type 2d/3d — ~13k سطر)
├── AdvancedParticleEmitter.json.bak# نسخة احتياطية قبل إصلاح Flow
├── sample_effect.json              # مثال export جاهز (83 سطر)
├── download.png                    # الأرت الأصلي (مصدر أيقونات assets)
├── carrot_debug.log                # تليمتري رنّات المستخدم (boot/gl-init/tickstat/exceptions)
├── package.json / package-lock.json# اعتماديات المعاينة (three + pixi + typescript + esbuild)
├── particle_core.pyd/.lib/.pdb     # نواة C++ المبنية (الـ .pyd هو المستخدم فعليًا)
├── Carrot Particle Editor.lnk      # شورتكت الويندوز (يُعاد توليده كل rebuild)
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

### الجذر

| الملف | الدور | الحجم | سطور |
|---|---|---:|---:|
| `particle_studio.py` | كل شيء: واجهة tkinter الداكنة، محاكاة Python الاحتياطية، ربط C++، فريمات GPU، سيرفر المعاينة، تصدير JSON، undo/redo، لوج `carrot_debug.log` | 137KB | 2683 |
| `rebuild_app.py` | `python rebuild_app.py` بعد أي تعديل: py_compile gate ← بناء C++ لو stale ← PyInstaller بالـ spec ← smoke boot 9 ثوانٍ ← توليد `.lnk` ← تنظيف `__pycache__` | 3KB | 71 |
| `CarrotParticleEditor.spec` | datas: `preview` + `assets` + `render` + `three.module.js` + `pixi.mjs` + `glfw3.dll` — hiddenimports: `particle_core, render.gl_view, glfw` — أيقونة `assets/app_icon.ico` — `console=False` | 1.3KB | 47 |
| `AdvancedParticleEmitter.json` | إكستنشن GDevelop كما هو (بدون إعادة تسمية `Avanced*`) — يدعم pyramid/torus + morph + تعبير Flow (مُصلَّح) | 525KB | ~13k |
| `AdvancedParticleEmitter.json.bak` | نسخة ما قبل الإصلاح (كانت تالفة وتم ترميمها) | 523KB | — |
| `sample_effect.json` | مثال export متوافق v1.0 | 1.7KB | 83 |
| `download.png` | الأرت الأصلي المرفوع من المستخدم — مصدر `assets/app_icon.*` | 1.4MB | — |
| `carrot_debug.log` | تليمتري: `boot b20260927-gl3` / `gl-init-ok` / `tickstat` / استثناءات — في `%TEMP%` عند المستخدم | 3.8KB | — |
| `package.json` | `three@0.186 + pixi.js@8.21 + typescript@7 + esbuild@0.28` | 191B | 11 |
| `particle_core.pyd` | نواة C++ المبنية فعليًا (يستخدمها `_tick` مع مؤشر C++/PY) | 461KB | — |
| `particle_core.lib/.pdb` | مخلفات بناء MSVC (غير مطلوبة للتشغيل) | — | — |
| `Carrot Particle Editor.lnk` | شورتكت: Target=`dist\CarrotParticleEditor.exe` + Icon=`assets\app_icon.ico` | 1.8KB | — |

### `core/` — نواة المحاكاة

| الملف | الدور | سطور |
|---|---|---:|
| `particle_core.cpp` | `step()` يخرج `x,y,z,r,color,shape,depth + alpha,wx,wy` — نفس `SHAPE_ORDER` (12 شكل) ونفس semantics الـ morph | 516 |
| `build_core.py` | ترتيب الكومبايلر: `cl > g++ > clang++ > Zig` (تثبيت تلقائي) — الخرج `particle_core.pyd` بجانب `particle_studio.py` | 83 |
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
| `dist/CarrotParticleEditor.exe` | التطبيق المتجمد (windowed) — يحمل كل تغيير بعد كل `rebuild_app.py` |

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
core/particle_core.cpp --build_core.py--> particle_core.pyd --step()--> particle_studio.py
                                                                              ├─ canvas (خلفية+شبكة tkinter)
                                                                              ├─ render/gl_view.py (GPU subrect → PPM → PhotoImage)
                                                                              ├─ preview/last_effect.json → live_effect.html (poll)
                                                                              └─ AdvancedParticleEmitter.json (export v1.0)
particle_studio.py + preview/ + assets/ + render/ --rebuild_app.py + .spec--> dist/CarrotParticleEditor.exe + .lnk
```

## 5) سير العمل المعتمد

1. عدّل أي ملف → 2. `python rebuild_app.py` (إجباري — الـ exe والشورتكت يحملان كل تغيير) → 3. جرّب من الشورتكت → 4. للمعاينة: من داخل الإديتور (القالب مضمّن، لا كاش قديم).
