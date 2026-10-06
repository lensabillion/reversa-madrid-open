---
type: is
id: is-01m48wve6ym387v8jpkn8f2tcd
title: "Public-site basics for the explorer: icon, not-found page, robots and link-preview metadata"
kind: feature
status: in_progress
priority: 2
version: 2
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T15:20:57.309Z
updated_at: 2026-10-06T15:21:05.366Z
started_at: 2026-10-06T15:21:05.365Z
---
Part 8 · Publish (the explorer). The explorer is served to the public but lacks what a public website needs: it has no site icon (browsers show a blank tab), an unmatched URL such as /atlas shows the black default Next.js 404 instead of a page in the explorer's visual language, there is no robots.txt telling crawlers the site is open, and a shared link shows no Open Graph or Twitter card preview. This bead adds frontend/app/icon.svg (a vector mark Next.js serves and links automatically), frontend/app/not-found.tsx (a server component with the explorer's header strip and a link back to /lineage), frontend/app/robots.ts (allow every user agent everything; the data is public), openGraph and twitter fields in frontend/app/layout.tsx with metadataBase read from INFLUENCE_PUBLIC_URL when a host sets it, and Vitest tests for each. Presentation only: no scoring logic, no new dependencies, nothing outside frontend/.
