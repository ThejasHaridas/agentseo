# AgentRank pitch video

`agentrank-pitch.mp4`: a 2-minute (119 s) 1080p30 sales pitch with a voiceover and an original soundtrack.

## Monologue

> The internet has a new kind of visitor.
>
> It doesn't scroll. It doesn't see your ads. It reads, compares, and decides, on behalf of your customers.
>
> ChatGPT. Claude. Perplexity. And browser agents that book, buy, and fill in forms. But most websites were built for people, and for Google. Not for them.
>
> Meet AgentRank. See your website the way AI agents do.
>
> One audit. Four questions. Can agents read it? Can agents use it? Do AI assistants recommend it? And how strong is your classic SEO?
>
> AgentRank crawls your site twice: raw HTML, and fully rendered in a real browser. It checks AI crawler access, structured data, and whether your prices, hours and contact details can actually be found.
>
> Then a live AI agent tries your site's key tasks, and records every step with a screenshot. So you see exactly where it got stuck. And it's safe. It never submits a booking, an order, or a payment.
>
> Next, it asks AI assistants the questions your customers ask. Are you named? Are you cited? And who gets recommended instead?
>
> You get a clear verdict, an Agent Ready score, and the score you'll reach after fixing. Plus ready to paste fixes: structured data, robots files, sitemaps, and meta tags. Each one linked to the problem it solves.
>
> Projects for every client. Agent replays. A 3D map of your site. And transparent, versioned scoring.
>
> Your next customer might not be a person. Make sure they can find you.
>
> AgentRank. Get agent ready.

The numbers, brands and domains shown on screen (score 46 → 88, "Northline Roasters", and so on) are
illustrative, not results from a real audit.

## How it is made

Everything runs offline; nothing is licensed from a stock library.

| File | Role |
| --- | --- |
| `script.json` | The monologue, one line per scene |
| `tts.mjs` | Voiceover with the open Kokoro-82M TTS model (Apache-2.0, voice `af_heart`), via `kokoro-js` + `kokoro-q8-shards` from npm |
| `timeline.json` | Start time and length of each line (the reveal lands on a bar of the 96 BPM track) |
| `music.py` | Synthesises the soundtrack with numpy (A minor pads, riser, drop on the logo reveal, groove, arpeggio, breakdown, final hit) and mixes it under the voice with ducking |
| `scene.html` | The motion graphics: a page with a deterministic `seek(t)` |
| `render.mjs` | Steps `seek(t)` at 30 fps in headless Chromium (Playwright) and pipes the frames to ffmpeg |

To re-render after editing the script (from this folder, with the npm packages above, numpy, Playwright and ffmpeg):

```sh
node tts.mjs script.json vo af_heart 1            # needs kokoro-q8.onnx (the joined shards) beside it
# recompute timeline.json from the new clip lengths, then:
python3 music.py                                   # writes mix.f32
ffmpeg -f f32le -ar 44100 -ac 2 -i mix.f32 -af loudnorm=I=-15:TP=-1 mix.wav
node render.mjs chunk 0 3582 video.mp4
ffmpeg -i video.mp4 -i mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest agentrank-pitch.mp4
```
