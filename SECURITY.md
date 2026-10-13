# Security policy

Report vulnerabilities privately to the repository owner. Do not open a public
issue containing credentials, personal data, exploit details, or lead records.

Supported production deployments use the current `main` branch with PostgreSQL,
TLS, explicit allowed hosts, rotated secrets, a restricted Google Places key,
and a restricted Vercel token.

Never commit `.env`, database files, QA artifacts, provider exports containing
personal data, or generated lead dossiers. All outreach remains approval-gated;
suppression and lawful-source controls must not be bypassed.
