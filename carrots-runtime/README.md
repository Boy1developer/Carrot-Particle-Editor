# `@carrot-studio/particle-runtime`

Typed TypeScript ingestion path for Carrot particle effect JSON (v1.0) —
built for **Carrots Game Engine** (GDJS runtime is TypeScript: PixiJS 2D /
Three.js 3D, JSON-based particle resources since engine `1.0.3`).

Strict `tsc` types + validation at the JSON boundary, so one bad field can
never poison the sim with `NaN`, and engine code never sees `any`.

## Use from a Carrots GDJS TypeScript extension

```ts
import {
  loadCarrotEffectFromJsonText,
  normalizeEffect,
} from "@carrot-studio/particle-runtime";

const res = await fetch("assets/fx/fire.json");
const effect = loadCarrotEffectFromJsonText(await res.text());
const runtime = normalizeEffect(effect);
// 2D: feed runtime.keyframes into the Pixi layer (needShape per state)
// 3D: feed runtime.keyframes into the Three layer (mesh swap per state)
```

`parseCarrotEffect` throws `CarrotEffectError` on structural problems
(not an object, missing/empty `states`); numeric fields fall back to
editor defaults and are clamped (`flow >= 0`, `maxParticles 1..4000`,
`spread 0..360`, `opacity 0..255`, durations `>= 1e-6`).

## Contracts (shared with the editor + `AdvancedParticleEmitter`)

- Format v1.0, `type: "2d" | "3d"`
- `SHAPE_ORDER` (12): circle, square, triangle, star, diamond, line,
  custom, sphere, cube, pyramid, torus, billboard
- Hyphenated easing: `linear` / `ease-in` / `ease-out` / `ease-in-out`
- Lifetime excludes the death-state duration (extension semantics)

## Develop

```bash
# from the repo root (uses the repo's TypeScript, no install needed)
node node_modules/typescript/bin/tsc -p carrots-runtime/tsconfig.json --noEmit
node node_modules/typescript/bin/tsc -p carrots-runtime/tsconfig.json
node carrots-runtime/test_loader.mjs
```

`dist/` is build output and stays out of git (see root `.gitignore`).
