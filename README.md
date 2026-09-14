# Cutting Plan & MTO — Streamlit

A Python/Streamlit tool for linear-material cutting plans and Material
Take-Off (MTO), backed by Supabase for auth and cloud project storage.

Live at: https://mycutting-plan.streamlit.app/

## What's included

- Sign in / sign up / forgot password via Supabase Auth
- Create / open / save projects to the cloud `projects` table
- Materials and cutting-piece editing via spreadsheet-style tables
- First-fit-decreasing cutting optimization, including multi-length stock
  support and kerf loss
- Cutting-plan bar visualization (matplotlib)
- Material Take-Off summary with stock balance / surplus
- Excel export (materials summary + per-material piece lists)
- Admin panel (gated to `supa.ADMIN_EMAIL`) for granting/revoking user access

## Not yet included

- PDF report generation
- Guest mode and per-guest usage limits
- Auto-save (there's a manual "Save to cloud" button in the sidebar instead)

## Running locally

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

By default it connects to the project's Supabase backend using a public
publishable key baked into `supa.py`. To point at a different Supabase
project, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
and fill in your own `SUPABASE_URL` / `SUPABASE_ANON_KEY`.

## Deploying

Deployed via [share.streamlit.io](https://share.streamlit.io), tracking the
`main` branch of this repo with main file path `app.py`. Pushing to `main`
triggers an automatic redeploy. Add `SUPABASE_URL` / `SUPABASE_ANON_KEY`
under the app's Secrets settings if you want to override the defaults.
