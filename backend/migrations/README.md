Schema v1 is defined by the SQLAlchemy models and created at startup via Base.metadata.create_all. For this local small application no destructive migration is run. Back up named db-data before modifying schemas.

Schema additions for channel-level DP review: `channels`, `audience_touches`, `privacy_budgets`, `privacy_releases`. All are additive and created by `create_all` on startup; existing tables are unchanged. `privacy_releases` keeps an immutable payload per version, and `privacy_budgets` holds the per-study epsilon ledger. Back up `db-data` before upgrading a live volume.
