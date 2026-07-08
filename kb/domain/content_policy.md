# Content Policy

Single source of truth for rating rules. Agents read this at runtime — rules
live here, not in code.

## Platform Overview

NexCurate is a game streaming platform serving three audience tiers:

- **Premium**: Enthusiast gamers, high engagement, full catalog access
- **Standard**: Mainstream gamers, curated selection, broad genres
- **Casual**: Light gamers and families, family-friendly content only

## Rating Policy

| Tier | Allowed Ratings | Blocked |
|------|-----------------|---------|
| premium | E, E10, T, M | AO |
| standard | E, E10, T, M | AO |
| casual | E, E10, T | M, AO |

Ratings follow the ESRB scale: E (Everyone), E10 (Everyone 10+), T (Teen),
M (Mature 17+), AO (Adults Only). AO is never permitted on any tier.

## Required Fields

Every published title row must carry: `id`, `title`, `genre`, `rating`.
