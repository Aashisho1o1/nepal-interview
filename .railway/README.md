# Deploy on Railway

`railway.ts` declares the whole project: Postgres and three services built from this
repo's `main` branch, all in Singapore.

| Service | What it runs | Public? |
|---|---|---|
| `web` | Next.js website (`apps/web`) | Yes, the only public service |
| `api` | FastAPI session API (`asgi.py`) | No: `web` proxies `/api/*` to it privately |
| `worker` | `python -m interview_api.reconcile --loop` | No |
| `postgres` | Railway Postgres | No |

Railway reads this file only when you run the CLI, never on deploy. Pushing to `main`
redeploys the services whose watched paths changed.

## First launch

1. Install the Railway CLI (5.42.1 or newer), then `railway login`.
2. In the Railway dashboard, create an empty project and give the Railway GitHub app
   access to `Aashisho1o1/nepal-interview`.
3. In that project, open Project Settings > Shared Variables (production) and add:
   `ELEVENLABS_AGENT_ID`, `ELEVENLABS_API_KEY`, `LIVEAVATAR_EMBED_URL`, and
   `ELEVENLABS_BRANCH_ID` if you use a branch. Enable authentication on the agent; the
   API refuses a public agent here. Add `TEAM_EMAILS` (founders' sign-in emails,
   comma-separated) to let them open `/team`, the review of every session.
4. From the repo root:

   ```bash
   npm install --prefix .railway
   railway link            # pick the project and the production environment
   railway config plan     # review: 1 database, 3 services, 1 group
   railway config apply
   ```

5. Open `web` > Settings > Networking > Generate Domain. Nothing else needs the
   address: the API accepts requests from whatever address the website is opened at.
6. Anyone can now create an account on the website. To also add the demo student
   (`student@synthetic.test`), run this inside the API container:

   ```bash
   railway ssh --service api
   export $(tr '\0' '\n' < /proc/1/environ | grep -E '^(PATH|DATABASE_URL|PYTHONPATH)=')
   SEED_PASSWORD='choose-one' python -m interview_api.seed
   ```

   The `export` line is needed in every SSH session: the shell doesn't load the
   server's environment, so `python` and the database settings are missing without it.
   Promo codes are created the same way (`python -m interview_api.plans ...`, see the
   main README).

7. Open the `web` address and sign in.

## Later changes

Edit `railway.ts`, then `railway config plan` and `railway config apply`. A resource
removed from the file is deleted on apply; the CLI marks it as destructive first.
Secrets stay in Shared Variables, never in this file.
