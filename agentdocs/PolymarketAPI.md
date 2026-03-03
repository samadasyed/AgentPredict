# Purpose

The Polymarket Data Agent collects public UFC market information from the Polymarket API and provides structured probability data to the reasoning system.

# Documentation:
https://docs.polymarket.com/api-reference/introduction

# Data Used
The agent reads publicly available market data to:

Discover UFC fight markets
Retrieve price history and recent price changes
Retrieve executed trade history
Read orderbook snapshots and midpoints
Access market metadata (outcomes and resolution conditions)
Prices in the range [0–1] are interpreted as implied win probabilities.

# Behavior
Locate relevant UFC markets
Continuously fetch recent market activity
Normalize responses into a simple event record:
{ timestamp, market_id, probability }
Send structured events to the explanation engine

# Operational Notes
Be efficient with API calls and use when its necessary
Cache discovered market IDs
Reconnect automatically on failure
Preserve raw responses for debugging

The agent acts as a live probability feed that the reasoning agent uses to understand market movement.
