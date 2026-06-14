# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please do **not** create a public GitHub issue.

Instead, send a report to the project maintainer with:

1. A description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if any)

You can expect an acknowledgment within 48 hours and a timeline for remediation within 5 business days.

## Security Best Practices for Deployers

- Always rotate API keys in `deploy/lighthouse/.env.prod` after initial deployment
- Keep `deploy/lighthouse/.env.prod` out of version control (verified by `.gitignore`)
- Review nginx security headers after each deployment (see `deploy/lighthouse/nginx.conf`)
- Enable C2PA content credentials (`C2PA_ENABLED=1`) before EU AI Act compliance deadline (2026-08-02)
- Set `CORS_ORIGINS` to your specific domain, not wildcard, in production
- Use HTTPS exclusively in production; the included nginx config redirects HTTP → HTTPS

## Environment Variables Containing Secrets

The following environment variables contain sensitive values and must never be committed to version control:

- `DEEPSEEK_API_KEY`
- `POYO_API_KEY`
- `SILICONFLOW_API_KEY`
- `SEEDANCE_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `ELEVENLABS_API_KEY`
- `DATABASE_URL`
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`
- `MEDIA_SIGN_SECRET`
- `WEBHOOK_URLS`
- `API_KEY`
- `TIKTOK_ACCESS_TOKEN`
- `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_API_PASSWORD`
- `FACEBOOK_ACCESS_TOKEN`

All of these are covered by `.gitignore` rules for `.env` and `.env.prod` files.
