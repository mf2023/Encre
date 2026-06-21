# Third-Party Acknowledgments

Dunimd is built upon the shoulders of many open source projects. We are deeply grateful to the maintainers and contributors of these projects.

---

## Core Runtime

| Project | License | Purpose |
|---|---|---|
| [Electron](https://electronjs.org) | MIT | Desktop application framework |
| [Node.js](https://nodejs.org) | Node.js License | JavaScript runtime |
| [Python](https://python.org) | PSF | Backend runtime |
| [Rust](https://rust-lang.org) | MIT / Apache 2.0 | Performance-critical components |
| [Cargo](https://doc.rust-lang.org/cargo) | MIT / Apache 2.0 | Rust package manager |

---

## Frontend (Electron App)

| Project | License | Purpose |
|---|---|---|
| [TypeScript](https://typescriptlang.org) | Apache 2.0 | Programming language |
| [esbuild](https://esbuild.github.io) | MIT | Bundler |
| [React](https://react.dev) | MIT | UI framework |
| [Monaco Editor](https://microsoft.github.io/monaco-editor) | MIT | Code editor |
| [xterm.js](https://xtermjs.org) | MIT | Terminal emulator |
| [highlight.js](https://highlightjs.org) | BSD 3-Clause | Syntax highlighting |
| [markdown-it](https://markdown-it.github.io) | MIT | Markdown rendering |
| [fuse.js](https://fusejs.io) | Apache 2.0 | Fuzzy search |
| [node-pty](https://github.com/microsoft/node-pty) | MIT | Pseudo-terminal allocation |
| [simple-icons](https://simpleicons.org) | CC0 1.0 | Icon library |

---

## Backend (Python)

### Core Dependencies

| Project | License | Purpose |
|---|---|---|
| [httpx](https://www.python-httpx.org) | BSD 3-Clause | HTTP client |
| [Pydantic](https://docs.pydantic.dev) | MIT | Data validation |
| [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | MIT | HTML/XML parsing |
| [markdownify](https://github.com/michaeljones/markdownify) | MIT | Markdown conversion |
| [lxml](https://lxml.de) | BSD 3-Clause | XML/HTML processing |
| [Tomli / Tomli-w](https://github.com/hukkin/tomli) | MIT | TOML parsing |
| [PyYAML](https://pyyaml.org/) | MIT | YAML parsing |
| [Cryptography](https://cryptography.io) | Apache 2.0 / BSD | Encryption utilities |
| [pathspec](https://github.com/cpburnz/python-path-specification) | BSD 2-Clause | Path pattern matching |
| [WebSockets](https://websockets.readthedocs.io) | BSD 3-Clause | WebSocket client/server |
| [Pillow](https://python-pillow.org) | HPND | Image processing |
| [Playwright](https://playwright.dev/) | Apache 2.0 | Browser automation |
| [tiktoken](https://github.com/openai/tiktoken) | MIT | Tokenization for LLMs |
| [NumPy](https://numpy.org) | BSD 3-Clause | Numerical computing |
| [Loguru](https://loguru.com) | MIT | Logging |
| [MSS](https://github.com/BoboPypy/mss) | MIT | Screen capture |
| [OpenPyXL](https://openpyxl.readthedocs.io) | MIT | Excel file processing |
| [pdfplumber](https://github.com/jalanbroadley/pdfplumber) | MIT | PDF text extraction |
| [PyAutoGUI](https://pyautogui.readthedocs.io) | BSD 3-Clause | GUI automation |
| [PyPDF / PyPDF2](https://pypdf2.readthedocs.io) | BSD 3-Clause | PDF processing |
| [Pytesseract](https://github.com/adam-p/markdown-here/raw/master/crossmark) | MIT | OCR via Tesseract |
| [uiautomation](https://github.com/pywinauto/uiautomation) | MIT | Windows UI automation |
| [Watchfiles](https://github.com/samuelcolvin/watchfiles) | MIT | File system watching |
| [DuckDuckGo Search](https://pypi.org/project/duckduckgo-search/) | MIT | Web search |
| [Zero API Key Web Search](https://pypi.org/project/zero-api-key-web-search/) | MIT | Web search API |

### Optional Dependencies

| Project | License | Purpose |
|---|---|---|
| [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) | MIT | Anthropic Claude integration |
| [Ollama](https://github.com/ollama/ollama-python) | MIT | Ollama integration |
| [aiohttp](https://docs.aiohttp.org) | Apache 2.0 | Async HTTP server |
| [discord.py](https://github.com/Rapptz/discord.py) | MIT | Discord bot integration |
| [Slack Bolt](https://github.com/slackhq/bolt-python) | MIT | Slack bot integration |
| [Slack SDK](https://github.com/slackapi/python-slack-sdk) | MIT | Slack API integration |
| [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | LGPLv3 | Telegram bot integration |
| [dingtalk-stream](https://github.com/dingtalk-stream/dingtalk-stream-sdk-python) | MIT | DingTalk integration |
| [aioimaplib](https://github.com/laurent-lacord/aioimaplib) | LGPLv3 | Async IMAP |
| [aiosmtplib](https://aiosmtplib.readthedocs.io) | BSD 3-Clause | Async SMTP |
| [PyTorch](https://pytorch.org/) | BSD 3-Clause | Machine learning |
| [Transformers](https://huggingface.co/docs/transformers) | Apache 2.0 | Hugging Face models |
| [Boto3](https://github.com/boto/boto3) | Apache 2.0 | AWS SDK |

---

## Rust Crates (Native Module)

| Project | License | Purpose |
|---|---|---|
| [serde](https://serde.rs) | MIT / Apache 2.0 | Serialization framework |
| [serde_json](https://docs.rs/serde_json) | MIT / Apache 2.0 | JSON serialization |
| [regex](https://docs.rs/regex) | MIT / Apache 2.0 | Regular expressions |
| [walkdir](https://docs.rs/walkdir) | Apache 2.0 / MIT | Directory traversal |
| [similar](https://docs.rs/similar) | Apache 2.0 | Text diffing |
| [glob](https://docs.rs/glob) | MIT / Apache 2.0 | Glob pattern matching |
| [tempfile](https://docs.rs/tempfile) | Apache 2.0 / MIT | Temporary files |
| [pyo3](https://github.com/PyO3/pyo3) | MIT / Apache 2.0 | Python bindings |
| [candle-core](https://github.com/huggingface/candle) | MIT / Apache 2.0 | ML inference (optional) |
| [tokenizers](https://github.com/huggingface/tokenizers) | Apache 2.0 | Tokenization (optional) |
| [wide](https://github.com/starkat99/wide-rs) | Apache 2.0 / MIT | SIMD intrinsics (optional) |

---

## Additional Notices

### Apache License 2.0

Some components of this software are licensed under the Apache License, Version 2.0. A copy of this license is available in the LICENSE file distributed with this software.

### MIT License

Some components of this software are licensed under the MIT License. Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

### BSD 3-Clause License

Some components of this software are licensed under BSD 3-Clause licenses. Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.

### HPND (Historical Permission Notice and Disclaimer)

Some components of this software are licensed under the HPND. Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met: Redistributions of source code must retain the above copyright notice and the full license text. Redistributions in binary form must reproduce the above copyright notice and the full license text in the documentation and/or other materials provided with the distribution.

### LGPLv3

Some components of this software are licensed under the GNU Lesser General Public License v3.0. Please refer to the individual package licenses for full details.

### CC0 1.0

Some components of this software are licensed under the CC0 1.0 Universal license (public domain).

### Node.js License

Some components of this software are licensed under the Node.js License. Please refer to https://github.com/nodejs/node/blob/main/LICENSE for full details.

---

*This document was automatically generated and may not be complete. For a complete list of dependencies and their licenses, please refer to the package.json, Cargo.toml, and pyproject.toml files distributed with this software.*
