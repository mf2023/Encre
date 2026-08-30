// Headless repro runner: loads the expand-repro page in Electron,
// simulates the expand toggle exactly like app.ts setInputExpanded,
// and dumps scroll metrics after each phase.
const { app, BrowserWindow } = require("electron");
const path = require("path");

const PAGE = path.join("D:/encre/measure-tmp/expand-repro/index.html");

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    show: false,
    width: 1280,
    height: 800,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  await win.loadFile(PAGE);
  await new Promise((r) => setTimeout(r, 300));

  const run = async (label) => win.webContents.executeJavaScript(label, true);

  try {
    // Phase 1: pinned-to-bottom expand (streaming scenario)
    let out = "";
    out += await run(`(async () => {
      const c = document.getElementById("chat-container");
      const btn = document.getElementById("btn-input-expand");
      const logs = [];
      const before = { scrollTop: c.scrollTop, clientH: c.clientHeight, scrollH: c.scrollHeight };
      btn.click();
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      await new Promise(r => setTimeout(r, 50));
      const after = { scrollTop: c.scrollTop, clientH: c.clientHeight, scrollH: c.scrollHeight };
      return JSON.stringify({
        phase: "EXPAND (pinned bottom)",
        before, after,
        scrollTopDelta: after.scrollTop - before.scrollTop,
        clientHDelta: after.clientH - before.clientH,
        scrollHDelta: after.scrollH - before.scrollH,
        pageLog: document.getElementById("log").textContent,
      }, null, 1);
    })()`);
    console.log("=== PHASE 1 ===");
    console.log(out);

    // Phase 2: collapse back
    out = await run(`(async () => {
      const c = document.getElementById("chat-container");
      const btn = document.getElementById("btn-input-expand");
      const before = { scrollTop: c.scrollTop, clientH: c.clientHeight, scrollH: c.scrollHeight };
      btn.click();
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      await new Promise(r => setTimeout(r, 50));
      const after = { scrollTop: c.scrollTop, clientH: c.clientHeight, scrollH: c.scrollHeight };
      return JSON.stringify({
        phase: "COLLAPSE",
        before, after,
        scrollTopDelta: after.scrollTop - before.scrollTop,
        clientHDelta: after.clientH - before.clientH,
        scrollHDelta: after.scrollH - before.scrollH,
      }, null, 1);
    })()`);
    console.log("=== PHASE 2 ===");
    console.log(out);

    // Phase 3: expand while scrolled UP (user inspecting an earlier message)
    out = await run(`(async () => {
      const c = document.getElementById("chat-container");
      const btn = document.getElementById("btn-input-expand");
      // scroll to ~30% like the user reading an old message
      c.scrollTop = Math.floor((c.scrollHeight - c.clientHeight) * 0.3);
      await new Promise(r => requestAnimationFrame(r));
      const before = { scrollTop: c.scrollTop, clientH: c.clientHeight, scrollH: c.scrollHeight };
      btn.click();
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      await new Promise(r => setTimeout(r, 50));
      const after = { scrollTop: c.scrollTop, clientH: c.clientHeight, scrollH: c.scrollHeight };
      return JSON.stringify({
        phase: "EXPAND (scrolled up 30%)",
        before, after,
        scrollTopDelta: after.scrollTop - before.scrollTop,
        clientHDelta: after.clientH - before.clientH,
        scrollHDelta: after.scrollH - before.scrollH,
      }, null, 1);
    })()`);
    console.log("=== PHASE 3 ===");
    console.log(out);

    // Phase 4: expand while status-bar just disappeared in the same frame
    out = await run(`(async () => {
      const c = document.getElementById("chat-container");
      const btn = document.getElementById("btn-input-expand");
      const sb = document.getElementById("chat-status-bar");
      // collapse first
      if (document.getElementById("input-area").classList.contains("input-expanded")) btn.click();
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      // pin bottom
      c.scrollTop = c.scrollHeight;
      await new Promise(r => requestAnimationFrame(r));
      const before = { scrollTop: c.scrollTop, clientH: c.clientHeight, scrollH: c.scrollHeight };
      // hide status bar AND click expand in the same tick (no layout between)
      sb.style.display = "none";
      btn.click();
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      await new Promise(r => setTimeout(r, 50));
      const after = { scrollTop: c.scrollTop, clientH: c.clientHeight, scrollH: c.scrollHeight };
      return JSON.stringify({
        phase: "EXPAND (status-bar hidden same-tick, pinned)",
        before, after,
        scrollTopDelta: after.scrollTop - before.scrollTop,
        clientHDelta: after.clientH - before.clientH,
        scrollHDelta: after.scrollH - before.scrollH,
      }, null, 1);
    })()`);
    console.log("=== PHASE 4 ===");
    console.log(out);
  } catch (e) {
    console.error("RUN FAILED:", e);
  } finally {
    app.quit();
  }
});
