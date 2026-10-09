# Football Identity Resolution Architecture — Sprint 2.3

## 1. Overview

Sprint 2.3 establishes a deterministic, auditable, and provider-independent identity-resolution system for football entities (competitions, seasons, teams).

It enforces the core architectural principle:

> **FALSE MERGES ARE WORSE THAN TEMPORARY DUPLICATES.**

When identity is uncertain:

The system returns `REVIEW_REQUIRED` for candidate review instead of performing dangerous automatic fuzzy merges.

---

## 2. Identity Resolution Pipeline Architecture

```
[ Provider External Identity (e.g. "Man United") ]
                       │
                       ▼
[ IdentityNormalizer ] (Unicode NFKD, case folding, preserved tokens: FC, United, City)
                       │
                       ▼
[ Stage 1: Explicit Provider Mapping Lookup ] ──(Found)──► [ RESOLVED_EXPLICIT_MAPPING ]
                       │ (Not Found)
                       ▼
[ Stage 2: Exact Normalized Canonical Name Match ] ──(Unique)──► [ RESOLVED_EXACT_NAME ]
                       │ (Not Found)
                       ▼
[ Stage 3: Exact Known Team Alias Match ] ──(Found)──► [ RESOLVED_ALIAS ]
                       │ (Not Found)
                       ▼
[ Stage 4: Similarity Candidate Generation ] ──(Candidates > Threshold)──► [ REVIEW_REQUIRED ]
                       │ (No Candidates)
                       ▼
[ Stage 5: Unambiguous Canonical Entity Creation ] ────────► [ NEW_CANONICAL_ENTITY ]
```

---

## 3. Resolution Decision Table

| Situation | Resolution Status | Action Taken |
|---|---|---|
| Exact `ProviderTeamMapping` match | `RESOLVED_EXPLICIT_MAPPING` | Use mapped canonical team ID immediately. |
| Exact unique canonical normalized match | `RESOLVED_EXACT_NAME` | Map to unique canonical team. |
| Exact `TeamAliasMapping` match | `RESOLVED_ALIAS` | Map to canonical team associated with alias. |
| High similarity candidates ($\ge 0.70$) | `REVIEW_REQUIRED` | Present candidates to human review. **DO NOT MERGE.** |
| Multiple exact normalized matches | `CONFLICT` | Block and flag exact name conflict. |
| No candidate match found | `NEW_CANONICAL_ENTITY` | Create new canonical team & mapping cleanly. |

---

## 4. False-Merge Prevention & Similarity Policy

* **Diagnostic Similarity Scoring:** `SimilarityEngine` calculates a 60/40 weighted combination of character SequenceMatcher ratio and Jaccard token set similarity (0.0 to 1.0).
* **Non-Auto-Merge Rule:** High similarity (e.g., `Manchester United` vs `Manchester City` or `Bristol City` vs `Bristol Rovers`) is used strictly to propose review candidates. It **NEVER automatically merges** canonical entities.

---

## 5. Team Identity Merger Engine (`TeamIdentityMerger`)

When duplicate teams are confirmed by human review:
1. `merge_teams(source_team_id, target_team_id)` migrates `home_team_id` and `away_team_id` references on matches, `MatchStatistic` records, `ProviderTeamMapping` entries, and `TeamAliasMapping` entries.
2. **Conflict Abort Safeguard:** Aborts transaction if merge creates a head-to-head match with `home_team_id == away_team_id` or duplicate match constraint violations.
3. **Audit Trails:** Preserves original source team with `is_active = False` and `short_code = 'MERGED'`, creating an audit record in `SystemAuditLog`.

---

## 6. Identity Readiness Gate (`assert_identity_ready`)

The readiness gate verifies:
* 0 exact duplicate normalized canonical team names.
* 0 provider mapping conflicts (single provider alias mapping to multiple canonical teams).
* 0 invalid foreign key references.

Raises `IdentityReadinessGateException` if blocking conflicts exist.

---

## 7. Developer CLI Commands

```bash
# 1. Run database identity audit
python scripts/football_identity.py audit

# 2. Resolve external provider team identity
python scripts/football_identity.py resolve --provider football_data_co_uk --external-name "Man United"

# 3. Explicitly create canonical team
python scripts/football_identity.py create-team --name "Manchester United FC" --country "England"

# 4. Add explicit team alias
python scripts/football_identity.py add-alias --team-id <canonical-uuid> --alias "Man Utd"

# 5. Inspect mappings for a canonical team
python scripts/football_identity.py mappings --team-id <canonical-uuid>

# 6. Safely merge source team B into target team A
python scripts/football_identity.py merge --source-team-id <source-uuid> --target-team-id <target-uuid>

# 7. Execute Identity Readiness Gate assertion
python scripts/football_identity.py verify-gate
```
