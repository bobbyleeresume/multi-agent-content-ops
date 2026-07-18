# Platform Tiers

| Tier | Audience | Catalog Scope | Regions |
|------|----------|---------------|---------|
| premium | Enthusiast gamers | Full catalog | NA, EU, APAC |
| standard | Mainstream gamers | Curated, broad genres | NA, EU, APAC |
| casual | Families / light gamers | Family-friendly only | NA, EU, APAC |

Adjusting a tier's rating policy needs only a `content_policy.md` edit.
Adding a new tier needs only a new row in the table above (plus a matching
row in `content_policy.md`'s Rating Policy table) — the CLI's `--tier`
choices are loaded from this file at runtime via
`policy.py::PolicyLoader.tiers()`, so no code change or deploy is required
(REFACTOR.md R3).
