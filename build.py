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

from __future__ import annotations

# ---------------------------------------------------------------------------
# Module summary
# ---------------------------------------------------------------------------
# Top-level build orchestrator for the Encre project.
#
# This script builds the native Rust extension, compiles the desktop TypeScript
# front-end, marks the prebuilt ``node-pty`` binary so Electron's rebuild is
# skipped, packages the desktop installer, and finally copies the produced
# installer artifacts to the repository root.
#
# Usage (run from the repository root):
#     python build.py          # full build
#     python build.py clean    # remove build artifacts
# ---------------------------------------------------------------------------

import os, platform, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NATIVE = ROOT / "native"
DESKTOP = ROOT / "desktop"
PY_PKG = ROOT / "backend" / "encre"
SERVER_DIST = ROOT / "build" / "server"  # PyInstaller output directory

IS_WIN = platform.system() == "Windows"
EXT = ".pyd" if IS_WIN else ".dylib" if platform.system() == "Darwin" else ".so"
SERVER_EXE = "encre-server.exe" if IS_WIN else "encre-server"

def run(cmd, **kw):
    """Run a shell command from the repository root, echoing it first.

    Args:
        cmd: The shell command string to execute.
        **kw: Extra keyword arguments forwarded to :func:`subprocess.run`.
    """
    print(f"$ {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=ROOT, **kw)

def build():
    """Run the full Encre build pipeline.

    Steps performed (in order):
      1. Compile the Rust native extension and copy it into the Python package.
      2. Bundle the Python backend into a standalone executable via PyInstaller.
      3. Build the desktop TypeScript front-end.
      4. Stamp a prebuilt ``node-pty`` marker so Electron source rebuild is skipped.
      5. Package the desktop installer via ``electron-builder``.
      6. Copy the resulting installer(s) to the repository root.
    """
    env = os.environ.copy()
    if sys.version_info >= (3, 14):
        env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"

    target_arch = os.environ.get("TARGET_ARCH", "x64")

    # 1. Rust 原生模块
    # Compile the Rust native extension in release mode for the encre-py crate.
    run(f"cd native && cargo build --release -p encre-py", env=env)
    src = next(iter(sorted((NATIVE/"target"/"release").glob("_native*"))), None)
    if src: shutil.copy2(src, PY_PKG / f"_native{EXT}")

    # 2. PyInstaller 打包 Python 后端
    # Bundle encre.server.app into a standalone executable with all dependencies.
    build_server()

    # 3. 桌面端 TypeScript 编译
    # Build the desktop TypeScript front-end via the project's build script.
    run("cd desktop && node build.js")

    # 4. 标记 node-pty 已编译（跳过 @electron/rebuild 源码编译）
    # Stamp the prebuilt node-pty binary so Electron's source rebuild is skipped.
    meta = DESKTOP / "node_modules" / "node-pty" / "build" / "Release" / ".forge-meta"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(f"{target_arch}--146")

    # 5. 打包安装程序
    # Package the desktop app into an installer (no publishing).
    # Pass target arch so only the runner's native arch is built.
    cmd = "cd desktop && npx electron-builder --publish never"
    if target_arch in ("arm64", "x64"):
        cmd += f" --{target_arch}"
    run(cmd)

    # 6. 复制安装包到根目录
    # Copy the produced installer(s) up to the repository root for easy access.
    for f in (DESKTOP/"release").glob("Encre*"):
        shutil.copy2(f, ROOT / f.name)
        print(f"  >>> {f.name}")

def build_server():
    """Bundle the Python backend into a standalone executable via PyInstaller.

    Produces ``build/server/encre-server[.exe]`` containing the full Python
    runtime, all encre modules, prompt templates, skill definitions, and the
    Rust native extension.  The resulting binary can be spawned by the
    Electron desktop app without requiring a system Python installation.
    """
    print("\n=== Building Python backend (PyInstaller) ===")

    # Ensure PyInstaller is available
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller...")
        run(f'"{sys.executable}" -m pip install pyinstaller')

    # Clean previous build
    if SERVER_DIST.exists():
        shutil.rmtree(SERVER_DIST)
    SERVER_DIST.mkdir(parents=True, exist_ok=True)

    # Collect data files: prompts, skills, dangerous_commands.txt
    datas = [
        (str(PY_PKG / "prompts"), "encre/prompts"),
        (str(PY_PKG / "skills" / "builtin"), "encre/skills/builtin"),
        (str(PY_PKG / "dangerous_commands.txt"), "encre"),
    ]

    # Include the Rust native extension if present
    native_ext = PY_PKG / f"_native{EXT}"
    if native_ext.exists():
        datas.append((str(native_ext), "encre"))

    # Build --add-data arguments
    sep = ";" if IS_WIN else ":"
    data_args = []
    for src, dst in datas:
        data_args.extend(["--add-data", f"{src}{sep}{dst}"])

    # Hidden imports that PyInstaller may not detect automatically
    hidden_imports = [
        "encre.adapters",
        "encre.backends",
        "encre.backends.registry",
        "encre.channels",
        "encre.tools",
        "encre.tools.builtin",
        "encre.tools.discovery",
        "encre.compact",
        "encre.memdir",
        "encre.swarm",
        "encre.evolution",
        "encre.hooks",
        "encre.sandbox",
        "encre.lsp",
        "encre.codebase",
        "encre.gateway",
        "encre.server",
        "encre.server.ws",
        "encre.server.admin",
        "encre.server.session_manager",
        "encre.prompts",
        "encre.skills",
        "encre.soul",
        "encre.profile",
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
        "numpy",
        "pydantic",
        "httpx",
        "websockets",
        "cryptography",
    ]
    hidden_args = []
    for mod in hidden_imports:
        hidden_args.extend(["--hidden-import", mod])

    # Exclude heavy optional dependencies to keep bundle smaller
    excludes = [
        "torch", "transformers", "tensorflow", "keras",
        "boto3", "botocore",
        "matplotlib", "scipy", "pandas",
        "tkinter", "unittest",
    ]
    exclude_args = []
    for mod in excludes:
        exclude_args.extend(["--exclude-module", mod])

    # Run PyInstaller
    cmd_parts = [
        f'"{sys.executable}"', "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", "encre-server",
        "--distpath", str(SERVER_DIST),
        "--workpath", str(ROOT / "build" / "pyinstaller-work"),
        "--specpath", str(ROOT / "build"),
        *data_args,
        *hidden_args,
        *exclude_args,
        "--contents-directory", "_internal",
        str(PY_PKG / "server" / "app.py"),
    ]
    run(" ".join(cmd_parts))

    # Verify output
    output_exe = SERVER_DIST / "encre-server" / SERVER_EXE
    if output_exe.exists():
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        print(f"  ✔ Backend bundled: {output_exe} ({size_mb:.1f} MB)")
    else:
        print(f"  ✖ ERROR: Expected output not found at {output_exe}")
        sys.exit(1)


def clean():
    """Remove all build artifacts produced by :func:`build`.

    Deletes the Rust ``target`` directory, the compiled native extension inside
    the Python package, desktop build outputs (``dist``, renderer assets,
    ``release``), the PyInstaller server bundle, and any installer artifacts
    at the repository root.
    """
    for d in [NATIVE/"target", ROOT/"build"]:
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
