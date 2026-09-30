# -*- coding: utf-8 -*-
"""Rebuild the browser-preview artifacts (documents the exact commands).

1. tsc in place: preview/*.ts -> preview/*.js (tests import the .js).
2. esbuild bundle: preview/main.ts -> preview/live_bundle.js (inlined by the
   editor into live_effect.html for the exe, which has no localhost).

Usage: python tools/build_preview.py
Requires: npm install (typescript, esbuild in node_modules).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSC = os.path.join(ROOT, "node_modules", "typescript", "bin", "tsc")
ESBUILD = os.path.join(ROOT, "node_modules", "esbuild", "bin", "esbuild")


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main():
    run([sys.executable, TSC, "-p", "preview/tsconfig.json"])
    run(["node", ESBUILD, "preview/main.ts", "--bundle", "--minify",
         "--format=esm", "--outfile=preview/live_bundle.js"])
    print("PREVIEW-BUILD-OK")


if __name__ == "__main__":
    main()
