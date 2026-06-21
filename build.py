#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

import os, platform, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NATIVE = ROOT / "native"
DESKTOP = ROOT / "desktop"
PY_PKG = ROOT / "backend" / "encre"

IS_WIN = platform.system() == "Windows"
EXT = ".pyd" if IS_WIN else ".dylib" if platform.system() == "Darwin" else ".so"

def run(cmd, **kw):
    print(f"$ {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=ROOT, **kw)

def build():
    env = os.environ.copy()
    if sys.version_info >= (3, 14):
        env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"

    # 1. Rust 原生模块
    run(f"cd native && cargo build --release -p encre-py", env=env)
    src = next(iter(sorted((NATIVE/"target"/"release").glob("_native*"))), None)
    if src: shutil.copy2(src, PY_PKG / f"_native{EXT}")

    # 2. 桌面端 TypeScript 编译
    run("cd desktop && node build.js")

    # 3. 标记 node-pty 已编译（跳过 @electron/rebuild 源码编译）
    meta = DESKTOP / "node_modules" / "node-pty" / "build" / "Release" / ".forge-meta"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text("x64--146")

    # 4. 打包安装程序
    run("cd desktop && npx electron-builder --publish never")

    # 5. 复制安装包到根目录
    for f in (DESKTOP/"release").glob("Encre*"):
        shutil.copy2(f, ROOT / f.name)
        print(f"  >>> {f.name}")

def clean():
    for d in [NATIVE/"target"]:
        if d.exists(): shutil.rmtree(d)
    for f in PY_PKG.glob("_native.*"): f.unlink()
    for p in [DESKTOP/"dist", DESKTOP/"renderer"/"vs",
              DESKTOP/"renderer"/"bundle.js", DESKTOP/"renderer"/"xterm.css",
              DESKTOP/"release"]:
        if p.exists(): shutil.rmtree(p) if p.is_dir() else p.unlink()
    for f in ROOT.glob("Encre*Setup*"): f.unlink()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean()
    else:
        build()
