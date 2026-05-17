const esbuild = require("esbuild");
const path = require("path");

const desktop = __dirname;

// Main process
esbuild.buildSync({
  entryPoints: [path.join(desktop, "main.ts")],
  bundle: true,
  platform: "node",
  target: "node20",
  outfile: path.join(desktop, "dist", "main.js"),
  external: ["electron"],
});

// Preload
esbuild.buildSync({
  entryPoints: [path.join(desktop, "preload.ts")],
  bundle: true,
  platform: "node",
  target: "node20",
  outfile: path.join(desktop, "dist", "preload.js"),
  external: ["electron"],
});

// Renderer
esbuild.buildSync({
  entryPoints: [path.join(desktop, "renderer", "src", "app.ts")],
  bundle: true,
  platform: "browser",
  target: "es2022",
  outfile: path.join(desktop, "renderer", "bundle.js"),
});

console.log("Build complete.");
