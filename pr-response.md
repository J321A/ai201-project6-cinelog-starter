# PR Response Doc — CineLog Watchlist Feature

This document responds to each of @dev-lead's six review comments on the
watchlist PR, records the reasoning behind every code change, and lays out the
two design decisions in full.

## AI Usage

I used an AI assistant in three bounded ways:

- **Orientation.** Before reading the review comments, I had the AI summarize
  `models.py`, `services/collection_service.py`, and `tests/test_collection.py`
  — what each file owns and what the functions return. I verified every claim
  against the code (e.g., confirmed `add_to_collection` raises
  `AlreadyInCollectionError` on a duplicate and `FilmNotFoundError` on a missing
  film, and that `get_collection` sorts by `date_added` DESC).
- **Pattern check for dedup (Comment 2).** I asked the AI to walk me through
  what `add_to_collection`'s duplicate check does and returns, then wrote my own
  `add_to_watchlist` check by hand mirroring that shape. I did not have it write
  the dedup code.
- **Stress-testing the design arguments (Comments 4 & 5).** After drafting both
  positions myself, I asked: "What counterargument would a careful reviewer
  raise, and what tradeoff am I not acknowledging?" For Comment 4 it pushed the
  "privacy by default" norm harder than my draft did, so I strengthened the
  tradeoff paragraph and pointed to the explicit `public` toggle and a planned
  per-user default as the mitigation. For Comment 5 it raised long-list
  discoverability, which I folded in as the future `sort` param. The positions
  and the CineLog-specific reasoning are my own.

## Comment 1 — Rename `save_to_watchlist` → `add_to_watchlist`

**What I did:** Renamed the service function to follow the project's
`verb_to_noun` convention (matching `add_to_collection`), and updated its one
call site in `routes/watchlist/watchlist.py` (both the import and the call).

**How I verified:** Project-wide search for `save_to_watchlist`
(`grep -rn save_to_watchlist .`) returned zero hits after the change; the full
test suite still passes.

## Comment 2 — Deduplication

**What I did:** Added an `AlreadyInWatchlistError` and, in `add_to_watchlist`,
a lookup for an existing `(user_id, film_id)` entry before inserting — raising
the error instead of creating a duplicate. This mirrors `add_to_collection`
exactly. I also added a `UniqueConstraint("user_id", "film_id")` on
`WatchlistEntry` as a database-level backstop, and the `/add` endpoint now
returns HTTP 409 on a duplicate.

**How I verified:** Modeled on `add_to_collection`'s check (looked at
`services/collection_service.py:47-53`). Added
`test_add_to_watchlist_duplicate_raises`, which confirms the second add raises
and that exactly one row exists. Also confirmed dedup is scoped per user, not
per film (see the extra test under Comment 3).

## Comment 3 — Missing test

**What I did:** Created `tests/test_watchlist.py` and wrote
`test_add_to_watchlist_nonexistent_film_raises`, the direct equivalent of
`test_add_to_collection_nonexistent_film_raises` — same `app`/`sample_user`
fixtures, same "expect `FilmNotFoundError` on a UUID that isn't in the DB"
assertion. I used that existing test as my model for fixture and assertion
structure.

**Extra tests (stretch — second test):** I also added
`test_watchlist_dedup_is_scoped_per_user`. I chose this edge case because the
most likely way to get deduplication *wrong* is to check "does any entry for
this film exist?" globally instead of per `(user_id, film_id)`. That bug
wouldn't surface in the single-user duplicate test but would silently block a
second user from saving a popular film — exactly the kind of thing a community
app must not do. The test adds the same film for two users and asserts both
succeed. (Plus tests for `remove_from_watchlist` success and the
not-present error path.)

**How I verified:** `pytest tests/ -v` — 9 passed (4 collection, 5 watchlist).

## Comment 4 — Default visibility (`public=True`)

**My position:** Keep the default `public=True`, but make it an *intentional*
default rather than an inherited one, and pair it with an explicit `public`
parameter so callers can opt out per entry.

**Reasoning (specific to CineLog):** CineLog is a *community* film-tracking app,
and a watchlist is a list of films a user *wants to watch* — an aspirational,
forward-looking signal, not a record of behavior. That distinction matters:
the collection (films watched, with 1–5 ratings) is the sensitive surface,
because it reveals what someone has actually done and how they judged it. A
watchlist mostly says "this looks interesting," which is low-sensitivity and
inherently social — "what's on your list?" is a conversation starter, and the
recommendations that make a community tracker valuable depend on those lists
being visible. Since the app is pre-launch (API-only, no frontend, no existing
users to surprise), this is exactly the moment to *set* the norm deliberately.
Defaulting watchlists to public maximizes the discovery and network effects
that make an early community product worth joining.

**Tradeoff acknowledged:** The strongest counterargument is "privacy by
default" — the modern norm is to expose nothing without explicit consent, and a
`public=True` default silently publishes every user's intentions. I take that
seriously, which is why the default is not the *only* control: I added an
explicit `public` parameter to `add_to_watchlist` and the `/add` endpoint
(stretch feature below) so any caller can create a private entry today, and I'm
flagging a follow-up for a **per-user default-visibility preference** so users
who want private-by-default can set it once. If the team weights privacy over
discovery, the *only* change needed is flipping the column default to `False` —
the mechanism already supports both. I'm recommending public because of
CineLog's community mission, but I've built it so that decision is cheap to
revisit.

## Comment 5 — Sort order

**My position:** Adopt the maintainer's preference — default watchlists to
**date added, newest first** — implemented in this PR
(`WatchlistEntry.date_added.desc()`).

**Reasoning:** I agree with the maintainer, and there's a second reason beyond
"most users want to see what they added recently": the collection already sorts
by `date_added` DESC (`get_collection`). Making the watchlist behave the same
way gives users one consistent mental model across both lists instead of two
different orderings to learn. It also fits *why* films land on a watchlist —
you usually add one right after hearing about it, so recency tracks intent, and
the film you're most likely to act on next is the one you just added.

**Engagement with the reviewer's point:** The reviewer's rationale ("most users
want to see what they added recently") is exactly right for the common case, so
I implemented it as the default rather than pushing back. The one case where
alphabetical wins is a *long* watchlist you're scanning for a specific title —
but watchlists tend to be short and recency-driven, and a scan-for-a-title need
is better served by search/filter than by changing the default sort for
everyone. So rather than trade the common case for the rare one, I'd propose a
follow-up `?sort=` query parameter (e.g. `date_added` default, `title`
optional) if long-list scanning becomes a real user need. Decision for now:
date-added, newest first.

## Comment 6 — Rebase onto updated main (integer IDs → UUIDs)

**What conflicted:** While the PR was open, a refactor merged to main
(`refactor: migrate film IDs from integer to UUID`) that changed `Film.id` (and
the foreign keys referencing it) from `db.Integer` to `db.String(36)`. My
branch had branched *before* that refactor, so `WatchlistEntry.film_id` was
still declared `db.Integer, db.ForeignKey("film.id")` — a type mismatch against
the new UUID `Film.id`. The service docstrings also still described `film_id` as
an integer.

**How I resolved it:** I rebased `feature/watchlist` onto the updated `main`
(`git fetch origin` / `git rebase origin/main`) and updated the watchlist code
to match the new UUID scheme: `WatchlistEntry.film_id` is now
`db.String(36), db.ForeignKey("film.id")`, and the service docstrings now
describe `film_id` as a UUID string. My test for the missing film already uses a
UUID-shaped id (`00000000-0000-0000-0000-000000000000`), consistent with the
collection test. The branch is rebased (linear on top of main) with **no merge
commits**.

**How I verified no conflict remains:** `git status` reported no conflict
markers and a clean tree; `git log --oneline --merges origin/main..HEAD` is
empty (no merge commits); `grep -rn "db.Integer" models.py` shows no integer
film/user id columns remain; and the full suite passes against the UUID schema.

---

## Screenshot — `git log --oneline`

Rewritten, conventional, linear history on top of `main` (no merge commits):

```
7035f25 docs: add pr-response.md with review responses and design decisions
8949ca1 test: add watchlist service tests
110d647 feat: add remove_from_watchlist and explicit visibility toggle
405a426 fix: order watchlist by date added (newest first) instead of alphabetical
bac7cf3 fix: update WatchlistEntry film_id to UUID after main branch refactor
aeb50b8 fix: add deduplication check to prevent duplicate watchlist entries
85fe0af fix: rename save_to_watchlist to add_to_watchlist per naming convention
4e9875f feat: add watchlist model, service, and REST endpoints
```

*(The `docs:` commit's short hash updates when this log is embedded into it;
the eight-commit, merge-free structure is what matters.)*

---

## PR Description

### What the watchlist feature does

Adds a **watchlist** so CineLog users can save films they *want to watch*
(distinct from the collection, which is films they've already watched and
rated). It ships:

- A `WatchlistEntry` model (`user_id`, `film_id` (UUID), `date_added`,
  `public`), with a unique `(user_id, film_id)` constraint.
- Service functions following the project's `verb_to_noun` convention:
  `add_to_watchlist(user_id, film_id, public=True)`,
  `remove_from_watchlist(user_id, film_id)`, and `get_watchlist(user_id)`
  (returns films newest-first).
- REST endpoints under `/watchlist`:
  - `GET  /watchlist/<user_id>` — list the user's watchlist (newest first)
  - `POST /watchlist/<user_id>/add` — body `{ "film_id": <uuid>, "public": <bool?> }`
  - `POST /watchlist/<user_id>/remove` — body `{ "film_id": <uuid> }`
- Deduplication (409 on a repeat add) and `FilmNotFoundError` handling (404).

### Design decisions made

1. **Default visibility = `public=True`** (Comment 4): optimizing for community
   discovery on a community-oriented app, since a watchlist is low-sensitivity
   "want to watch" data. Mitigated by an explicit `public` toggle and a planned
   per-user default preference. Flipping to private-by-default is a one-line
   change if the team prefers.
2. **Default sort = date added, newest first** (Comment 5): adopted the
   maintainer's preference; also matches `get_collection` for a consistent
   mental model. A future `?sort=` param can cover alphabetical.

### How to manually test

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # serves http://127.0.0.1:5000 (API only; / returns 404)
```

You need a real user id and film id (UUIDs). Create them via the films/users
paths or a quick Flask shell, then:

```bash
# Add a film to the watchlist (public defaults to true)
curl -s -X POST http://127.0.0.1:5000/watchlist/<USER_ID>/add \
     -H "Content-Type: application/json" \
     -d '{"film_id": "<FILM_ID>"}'

# Add privately (explicit visibility toggle)
curl -s -X POST http://127.0.0.1:5000/watchlist/<USER_ID>/add \
     -H "Content-Type: application/json" \
     -d '{"film_id": "<FILM_ID>", "public": false}'

# Duplicate add -> 409
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
     http://127.0.0.1:5000/watchlist/<USER_ID>/add \
     -H "Content-Type: application/json" -d '{"film_id": "<FILM_ID>"}'

# Nonexistent film -> 404
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
     http://127.0.0.1:5000/watchlist/<USER_ID>/add \
     -H "Content-Type: application/json" \
     -d '{"film_id": "00000000-0000-0000-0000-000000000000"}'

# View the watchlist (newest first)
curl -s http://127.0.0.1:5000/watchlist/<USER_ID>

# Remove a film
curl -s -X POST http://127.0.0.1:5000/watchlist/<USER_ID>/remove \
     -H "Content-Type: application/json" -d '{"film_id": "<FILM_ID>"}'
```

Or run the automated suite: `pytest tests/ -v` (9 passing).
