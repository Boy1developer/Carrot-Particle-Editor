import { ParticleEngine } from "./preview.js";
import { readFileSync } from "fs";

const base = JSON.parse(readFileSync(new URL("../sample_effect.json", import.meta.url), "utf8"));
const e = new ParticleEngine();

// custom-shaped states with model refs + embedded blobs
const eff = JSON.parse(JSON.stringify(base));
eff.type = "3d";
eff.states = [
  { id: "s0", role: "birth", label: "b", duration: 0.5, shape: "custom",
    easing: "linear", appearance: { size: 8, color: "#ffffff", opacity: 255 },
    movement: { minSpeed: 0, maxSpeed: 0 }, modelRefs: ["coin"] },
  { id: "s1", role: "death", label: "d", duration: 0.5, shape: "custom",
    easing: "linear", appearance: { size: 4, color: "#ffffff", opacity: 255 },
    movement: { minSpeed: 0, maxSpeed: 0 }, modelRefs: ["coin"] },
];
eff.modelsData = { coin: { mime: "model/gltf-binary", data: "QUJD" } };
e.loadEffect(eff);
if (JSON.stringify(e.customRefs()) !== JSON.stringify(["coin"])) {
  console.error("FAIL: customRefs", e.customRefs()); process.exit(1);
}
const blob = e.modelBlob("coin");
if (!blob || blob.mime !== "model/gltf-binary" || blob.data !== "QUJD") {
  console.error("FAIL: modelBlob", blob); process.exit(1);
}
if (e.modelBlob("nope") !== null) { console.error("FAIL: missing blob"); process.exit(1); }
if (e.modelRefAt(0.0) !== "coin" || e.modelRefAt(0.49) !== "coin") {
  console.error("FAIL: modelRefAt", e.modelRefAt(0.0)); process.exit(1);
}

// live poll WITHOUT modelsData must keep previously cached blobs
const poll = JSON.parse(JSON.stringify(eff));
delete poll.modelsData;
e.loadEffect(poll);
if (e.modelBlob("coin") === null) { console.error("FAIL: blobs wiped by poll"); process.exit(1); }

// explicit empty modelsData clears the cache (model removed upstream);
// state refs stay (they come from states), only bytes are dropped
const cleared = JSON.parse(JSON.stringify(poll));
cleared.modelsData = {};
e.loadEffect(cleared);
if (e.modelBlob("coin") !== null) { console.error("FAIL: blobs not cleared"); process.exit(1); }
if (JSON.stringify(e.customRefs()) !== JSON.stringify(["coin"])) {
  console.error("FAIL: refs after clear", e.customRefs()); process.exit(1);
}

// states without modelRefs -> empty ref, no crash
const plain = JSON.parse(JSON.stringify(base));
e.loadEffect(plain);
if (e.modelRefAt(0) !== "") { console.error("FAIL: empty ref"); process.exit(1); }
console.log("MODELS OK");
