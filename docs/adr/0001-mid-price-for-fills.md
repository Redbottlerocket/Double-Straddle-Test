# Use Mid Price for All Entry and Exit Fills

All backtest fills (entry, near-term exit, far-term exit) use the end-of-day mid price (average of bid and ask) rather than bid or ask.

Realistic fills would use the ask when buying and the bid when selling, which widens P&L by the full bid-ask spread on every leg. Mid is optimistic but is the standard convention for strategy-level backtesting where the goal is signal quality, not execution simulation. Slippage analysis (bid/ask fills) is reserved for a later sensitivity pass.
