# Re-pull cbbo-1m with tight EOD window for clean closing snapshots

We discovered that the original `cbbo-1m` pull captured "the last bar at or after 4 PM ET", which produces stale quotes for illiquid strikes (e.g., TSLA $725 call on Apr 22 2020 reflected an 11 AM stock price of $725, not the $687 close).

We initially planned to re-pull at `cbbo-1h` (hourly snapshots) to slash cost and avoid filter logic entirely, but Databento doesn't expose `cbbo-1h` for OPRA.PILLAR — valid intervals are only `cbbo-1s` and `cbbo-1m`. `cbbo-1s` is ~60x more expensive than necessary.

So we re-pull at the same `cbbo-1m` schema (~$0.78 for AAPL, ~$18 for the full universe) but apply a tighter reduction: only keep the last bar whose timestamp falls in the final 5 minutes before 4:00 PM ET. If no bar exists in that window we drop the row entirely instead of falling back to a stale mid-day quote.

Raw Databento responses are persisted to `data/raw/<ticker>_cbbo_1m.parquet` so future EOD filter changes (e.g., narrowing the window further) don't require another paid pull. See [[feedback-keep-raw-data]].
