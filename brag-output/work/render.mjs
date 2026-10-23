// Renders brag.html frame by frame: every frame is a pure function of time.
import { createRequire } from "module";
import { spawn } from "child_process";
import fs from "fs";
const require = createRequire("/opt/node22/lib/node_modules/");
const { chromium } = require("playwright");
const [, , mode, ...args] = process.argv;
const FPS = 30, TOTAL = 20;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on("pageerror", (e) => console.error("PAGE ERROR", e.message));
await page.goto("file://" + process.cwd() + "/brag.html");
await page.evaluate(async () => { await document.fonts.ready; });
if (mode === "stills") {
  fs.mkdirSync("stills", { recursive: true });
  for (const t of args.map(Number)) {
    await page.evaluate((t) => window.seek(t), t);
    await page.screenshot({ path: `stills/t${t.toFixed(2).padStart(5, "0")}.jpg`, type: "jpeg", quality: 80 });
  }
} else {
  const ff = spawn("ffmpeg", ["-v", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p", "video.mp4"], { stdio: ["pipe", "inherit", "inherit"] });
  for (let f = 0; f < FPS * TOTAL; f++) {
    await page.evaluate((t) => window.seek(t), f / FPS);
    const buf = await page.screenshot({ type: "jpeg", quality: 94 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
  }
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
}
await browser.close();
