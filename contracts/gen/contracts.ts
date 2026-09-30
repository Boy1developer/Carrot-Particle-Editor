// DO NOT EDIT — generated from contracts/contracts.json by tools/generate_contracts.py.
// Import path (preview + carrots-runtime tsconfigs allow ../contracts):
//   import { SHAPE_ORDER } from "../../contracts/gen/contracts";
export const EXPORT_VERSION = "1.0" as const;
export const RECORD_FIELDS = [
  "x",
  "y",
  "vx",
  "vy",
  "age",
  "c0",
  "c1",
  "s0",
  "s1",
  "life",
  "z",
  "vz",
  "shape",
  "tracks",
  "dx",
  "dy",
  "dz",
  "gx",
  "gy",
  "gz",
  "sizeRatio",
  "speedRatio",
] as const;
export const SHAPE_ORDER = [
  "circle",
  "square",
  "triangle",
  "star",
  "diamond",
  "line",
  "custom",
  "sphere",
  "cube",
  "pyramid",
  "torus",
  "billboard",
] as const;
export type ShapeName = (typeof SHAPE_ORDER)[number];
export const SHAPES_2D = [
  "circle",
  "square",
  "triangle",
  "star",
  "diamond",
  "line",
  "custom",
] as const;
export const SHAPES_3D = [
  "sphere",
  "cube",
  "pyramid",
  "diamond",
  "torus",
  "square",
  "triangle",
  "star",
  "line",
  "billboard",
  "custom",
] as const;
export const EASINGS = [
  "linear",
  "ease-in",
  "ease-out",
  "ease-in-out",
] as const;
export type Easing = (typeof EASINGS)[number];
export const EASING_ALIASES: Record<string, string> = {
  "easeIn": "ease-in",
  "easeOut": "ease-out",
  "easeInOut": "ease-in-out"
};
export const BLEND_MODES = [
  "Normal",
  "Additive",
  "Subtractive",
  "Multiply",
] as const;
export type BlendMode = (typeof BLEND_MODES)[number];
export const MORPH_LO = 0.25;
export const MORPH_HI = 0.75;
