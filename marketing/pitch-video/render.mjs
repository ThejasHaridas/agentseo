import { createRequire } from "module";
import { spawn } from "child_process";
import fs from "fs";
const require = createRequire("/opt/node22/lib/node_modules/");
const { chromium } = require("playwright");

const [,, mode, ...args] = process.argv;
const tl = JSON.parse(fs.readFileSync("timeline.json", "utf8"));
const FPS = 30;
const browser = await chromium.launch();

async function newPage() {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => console.error("PAGE ERROR", e.message));
  await page.goto("file://" + process.cwd() + "/scene.html");
  await page.evaluate(async (tl) => { await document.fonts.ready; window.init(tl); }, tl);
  return page;
}

if (mode === "stills") {
  const page = await newPage();
  fs.mkdirSync("stills", { recursive: true });
  for (const t of args.map(Number)) {
    await page.evaluate(([t, f]) => window.seek(t, f), [t, Math.round(t * FPS)]);
    await page.screenshot({ path: `stills/t${t.toFixed(1).padStart(5, "0")}.jpg`, type: "jpeg", quality: 80 });
  }
} else {
  // render a chunk of frames [from, to) into a segment
  const [from, to, out] = [Number(args[0]), Number(args[1]), args[2]];
  const page = await newPage();
  const ff = spawn("ffmpeg", ["-v", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", out], { stdio: ["pipe", "inherit", "inherit"] });
  for (let f = from; f < to; f++) {
    await page.evaluate(([t, f]) => window.seek(t, f), [f / FPS, f]);
    const buf = await page.screenshot({ type: "jpeg", quality: 93 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    if (f % 300 === 0) console.log(out, f);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
}
await browser.close();
