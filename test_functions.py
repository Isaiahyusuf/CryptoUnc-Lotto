#!/usr/bin/env python3
"""Quick test of leaderboard and recent draws functions"""

import os
os.environ['DATABASE_URL'] = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/dbname')

from main import get_top_winners, get_recent_draws_with_verification

print("="*60)
print("TESTING TRANSPARENCY DASHBOARD FUNCTIONS")
print("="*60)

print("\n1️⃣ Testing get_top_winners()...")
try:
    winners = get_top_winners(10)
    print(f"✅ SUCCESS: Found {len(winners)} winners")
    for w in winners:
        print(f"   - {w['username']}: {w['total_won']} SOL ({w['wins']} wins)")
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n2️⃣ Testing get_recent_draws_with_verification()...")
try:
    draws = get_recent_draws_with_verification(10)
    print(f"✅ SUCCESS: Found {len(draws)} draws")
    for d in draws:
        print(f"   - Round {d['round_id']}: Winner {d['winner_id']}, Prize {d['prize_amount']} SOL")
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
