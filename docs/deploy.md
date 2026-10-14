# Deploy

usched runs as one free [Render](https://render.com) web service with the
advisor on Gemini's free tier. Plans still live in each visitor's browser; the
server only reads the catalog. This page walks through the first deployment,
updates, and teardown.

## How it fits together

```txt
npm run catalog -- fetch build publish ─▶ GitHub release "catalog" ─┐ CATALOG_URL
git push main ─▶ GitHub Actions "check" ─▶ Render builds the Dockerfile ◀┘
                                         ─▶ https://<name>.onrender.com
```

- The **catalog** is never committed. You build it on your machine and publish
  it to this repository's `catalog` release. The Docker build downloads it.
- **CI** (`.github/workflows/check.yml`) runs `npm run check` and builds the
  client stage of the image on every push and pull request.
- **Render** reads `render.yaml`, and deploys a push to `main` only after its
  GitHub checks pass (`autoDeployTrigger: checksPass`).

The service uses Render's free plan, Gemini's free tier, and an
`onrender.com` address.

## Before you begin

You need:

- A Render account. It's free; sign in with GitHub.
- A Gemini API key from [Google AI Studio](https://aistudio.google.com). A
  free-tier key never bills you.
- The [GitHub CLI](https://cli.github.com), signed in with `gh auth login`.
- The fetcher's browser, installed once:

  ```bash
  uv run playwright install chromium
  ```

## Deploy for the first time

1. **Choose the address.** Render names the address after the service:
   `render.yaml` calls it `usched`, so you get `usched.onrender.com` if that
   name is free, otherwise Render adds a suffix. To pick another name, change
   `name:` in `render.yaml` (or in the Blueprint form) before you create the
   service. Treat the subdomain as fixed once the service exists.

2. **Publish the catalog.** Fetch fresh data, build and verify the database,
   and upload it:

   ```bash
   npm run catalog -- fetch build publish
   ```

   The command prints the `CATALOG_URL` the deployment downloads from.

3. **Optional: check production locally.** Run `npm run start`, then open
   <http://localhost:8000>. This is the same server the image runs.

4. **Create the service.** In Render, select **New > Blueprint** and pick this
   repository. Render reads `render.yaml` and asks for three values:

   | Variable         | Value                                         |
   | :--------------- | :-------------------------------------------- |
   | `CATALOG_URL`    | The URL step 2 printed.                       |
   | `GEMINI_API_KEY` | Your key.                                     |
   | `GEMINI_MODELS`  | `gemini-3.5-flash-lite,gemini-3.1-flash-lite` |

   Click **Apply**. The first build takes a few minutes; the service page
   shows the public URL.

5. **Smoke test** the public URL:
   - The page loads and a course search returns results.
   - `https://<name>.onrender.com/api/health` answers `{"status": "ok"}`.
   - The advisor answers one question.

## Keep it awake

Free services sleep after 15 idle minutes and take about a minute to wake;
the loading screen says "Waking up the course catalog…" meanwhile. Before a
demo, add a free [UptimeRobot](https://uptimerobot.com) HTTP monitor on
`https://<name>.onrender.com/api/health` every 5 minutes. Render's 750 free
hours a month cover one service running all month.

## Update

- **Code:** merge to `main`. Render deploys once CI passes.
- **Course data:** each new term, or whenever listings should refresh, rerun
  step 2, then select **Manual Deploy > Deploy latest commit** on Render.

## Limits

Each Flash-Lite model allows 15 requests a minute on the free tier, and an
advisor message takes one to three. Each model in `GEMINI_MODELS` has its own
quota, so listing two doubles it. Past the limit, the advisor says it is busy
for a minute.

Google may use free-tier prompts to improve its models. Prompts carry course
codes and plans, never names.

## Troubleshoot

| Symptom                                    | Fix                                                          |
| :----------------------------------------- | :----------------------------------------------------------- |
| Build fails asking for `CATALOG_URL`       | Publish the catalog (step 2) and set the URL it prints.      |
| Render rejects `autoDeployTrigger` on sync | Replace it with `autoDeploy: true` in `render.yaml`.         |
| A push to `main` doesn't deploy            | Check the `check` workflow on GitHub; Render waits for it.   |
| Advisor asks for a key or `GEMINI_MODELS`  | Set it in **Render > Environment**, then redeploy.           |
| Advisor says Gemini couldn't answer (400)  | The key or a model name is wrong; check both.                |
| Advisor is often busy                      | Add another Flash-Lite model to `GEMINI_MODELS`.             |
| The page takes a minute to load            | The service was asleep; see [Keep it awake](#keep-it-awake). |

## Take it down

1. Delete the service on Render, and the UptimeRobot monitor if you made one.
2. Optional: remove the published database with `gh release delete catalog`.

## Run the image elsewhere

The image is a plain Docker image and runs on any host that sets `PORT`:

```bash
docker build --build-arg CATALOG_URL=https://… -t usched .
docker run -p 8000:8000 --env-file .env usched
```
