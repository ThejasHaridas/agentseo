// Renders brag.html frame by frame: every frame is a pure function of time.
import { createRequire } from "module";
import { spawn } from "child_process";
import fs from "fs";
const require = createRequire("/opt/node22/lib/node_modules/");
const { chromium } = require("playwright");
const [, , mode, ...args] = process.argv;
// BRAG_VARIANT=vertical renders the 9:16, 50 s cut
const V = process.env.BRAG_VARIANT === "vertical";
const FPS = 30, TOTAL = V ? 50 : 20, W = V ? 1080 : 1920, H = V ? 1920 : 1080;
const PAGE = V ? "brag-vertical.html" : "brag.html", OUT = V ? "video_vertical.mp4" : "video.mp4", STILLS = V ? "stills_v" : "stills";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: W, height: H } });
page.on("pageerror", (e) => console.error("PAGE ERROR", e.message));
await page.goto("file://" + process.cwd() + "/" + PAGE);
await page.evaluate(async () => { await document.fonts.ready; });
if (mode === "stills") {
  fs.mkdirSync(STILLS, { recursive: true });
  for (const t of args.map(Number)) {
    await page.evaluate((t) => window.seek(t), t);
    await page.screenshot({ path: `${STILLS}/t${t.toFixed(2).padStart(5, "0")}.jpg`, type: "jpeg", quality: 80 });
  }
} else {
  const ff = spawn("ffmpeg", ["-v", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p", OUT], { stdio: ["pipe", "inherit", "inherit"] });
  for (let f = 0; f < FPS * TOTAL; f++) {
    await page.evaluate((t) => window.seek(t), f / FPS);
    const buf = await page.screenshot({ type: "jpeg", quality: 94 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
  }
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
}
await browser.close();
