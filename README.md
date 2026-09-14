# Cutting Plan & MTO — Streamlit

A Python/Streamlit rendition of the [Cutting Plan & MTO](https://cuttingnestpro.netlify.app/)
tool. It shares the same Supabase backend (auth, `profiles`, `user_plans`,
`projects` tables), so an account and saved projects created here also work
in the web app, and vice versa.

## What's included (MVP)

- Sign in / sign up via Supabase Auth
- Create / open / save projects to the cloud `projects` table
- Materials and cutting-piece editing via spreadsheet-style tables
- First-fit-decreasing cutting optimization (ported from `web/script.js`),
  including multi-length stock support and kerf loss
- Cutting-plan bar visualization (matplotlib)
- Material Take-Off summary with stock balance / surplus
- Excel export (materials summary + per-material piece lists)

## Not yet ported from the web app

- PDF report generation
- Admin panel (granting/revoking plans)
- Guest mode and per-guest usage limits
- Auto-save (there's a manual "Save to cloud" button in the sidebar instead)

## Running locally

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

By default it connects to the same Supabase project the Netlify app uses.
To point at a different project, copy `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml` and fill in your own `SUPABASE_URL` /
`SUPABASE_ANON_KEY`.

## Deploying

Push this repo to GitHub, then deploy on [share.streamlit.io](https://share.streamlit.io)
pointing at `streamlit_app/app.py`. Add `SUPABASE_URL` / `SUPABASE_ANON_KEY`
under the app's Secrets settings if you want to override the defaults.
