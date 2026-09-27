import { readFile } from "node:fs/promises";
import {
  loadCarrotEffectFromJsonText,
  normalizeEffect,
} from "./dist/index.js";

const sampleUrl = new URL("../sample_effect.json", import.meta.url);
const effect = loadCarrotEffectFromJsonText(await readFile(sampleUrl, "utf8"));
const norm = normalizeEffect(effect);
console.log(
  `states=${effect.states.length} type=${effect.type} ` +
    `flow=${norm.emitter.flow} totalDuration=${norm.totalDuration.toFixed(3)}`,
);

let threw = false;
try {
  loadCarrotEffectFromJsonText("{not json");
} catch {
  threw = true;
}
if (!threw) throw new Error("expected invalid JSON to throw");
console.log("invalid-json-throws=ok");

let emptyThrew = false;
try {
  loadCarrotEffectFromJsonText('{"version":"1.0","type":"2d","states":[]}');
} catch {
  emptyThrew = true;
}
if (!emptyThrew) throw new Error("expected empty states to throw");
console.log("empty-states-throws=ok");
