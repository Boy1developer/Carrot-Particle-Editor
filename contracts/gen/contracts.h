// DO NOT EDIT — generated from contracts/contracts.json by tools/generate_contracts.py.
#pragma once

// Export format version (must match effect JSON "version").
constexpr const char* CARROT_EXPORT_VERSION = "1.1";

// Particle record layout: 22 fields (see RECORD_FIELDS).
constexpr int CARROT_RECORD_FIELD_COUNT = 22;

constexpr int CARROT_SHAPE_COUNT = 12;
constexpr const char* CARROT_SHAPE_ORDER[CARROT_SHAPE_COUNT] = {"circle", "square", "triangle", "star", "diamond", "line", "custom", "sphere", "cube", "pyramid", "torus", "billboard"};

constexpr int CARROT_EASING_COUNT = 4;
constexpr const char* CARROT_EASINGS[CARROT_EASING_COUNT] = {"linear", "ease-in", "ease-out", "ease-in-out"};

constexpr int CARROT_BLEND_MODE_COUNT = 7;
constexpr const char* CARROT_BLEND_MODES[CARROT_BLEND_MODE_COUNT] = {"Normal", "Additive", "Subtractive", "Multiply", "Screen", "Lighten", "Overlay"};

// Shape cross-fade window (raw segment time).
constexpr double CARROT_MORPH_LO = 0.25;
constexpr double CARROT_MORPH_HI = 0.75;
