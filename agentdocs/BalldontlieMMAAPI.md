# Overview 

This module connects to the BallDontLie MMA API to fetch live UFC fight statistics and normalize them into EventObjects for the Central Engine.

Documentation: https://mma.balldontlie.io/?python#get-fight-statistics

API Tier Required GOAT Tier ($39.99/mo) needed for fight statistics endpoints. But right now just use the free tier, let me know if you need login details or anything. 

# Data Used 
The agent reads live fight data to:

Discover active UFC events
Retrieve fight-by-fight statistics
Track significant strikes, takedowns, knockdowns, and submissions
Monitor control time and round-by-round performance

# Behavior
Locate live UFC fights from events endpoint
Poll fight statistics during active bouts
Detect meaningful changes in fight metrics
Normalize responses into simple event records with timestamp, fight_id, fighter, and action type
Send structured events to the Central Engine
# Operational Notes
Be efficient with API calls
Cache fight IDs and previous stat snapshots
Stop polling completed fights automatically
Reconnect automatically on failure

The agent acts as a live fight statistics feed that the reasoning agent uses to correlate with market movements.