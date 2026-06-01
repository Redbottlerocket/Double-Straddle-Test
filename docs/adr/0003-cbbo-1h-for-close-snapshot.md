# Use cbbo-1h for the EOD closing snapshot

We discovered that the original `cbbo-1m` pull captured "the last bar at or after 4 PM ET", which produces stale quotes for illiquid strikes (e.g., TSLA $725 call on Apr 22 2020 reflected an 11 AM stock price of $725, not the $687 close). Re-pulling `cbbo-1m` for all 25 stocks to reduce with a stricter filter (15:55–16:00 ET) costs ~$18 again. Re-pulling at `cbbo-1h` instead is ~$0.30 for the full universe and gives one bid/ask snapshot per hour — the 4:00 PM ET bar IS the closing snapshot we want, no filter logic needed.

Trade-off: we lose the ability to do any intraday analysis from the new pull. We're keeping the original `cbbo-1m` parquet, so that flexibility remains available historically but won't be backfilled going forward.

Raw Databento responses are now persisted to `data/raw/` so future EOD filter changes don't require another paid pull. See [[feedback-keep-raw-data]].
