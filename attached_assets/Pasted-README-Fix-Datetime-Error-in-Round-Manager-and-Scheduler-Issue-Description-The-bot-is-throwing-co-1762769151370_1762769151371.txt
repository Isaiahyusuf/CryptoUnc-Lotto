README: Fix Datetime Error in Round Manager and Scheduler

Issue Description:
The bot is throwing continuous errors during round management:
“TypeError: can’t subtract offset-naive and offset-aware datetimes.”
This happens when the code tries to subtract a datetime that has timezone info (offset-aware) from one that doesn’t (offset-naive). It prevents the Round Manager and Scheduler from running correctly.

Objective:
Fix all datetime handling across the bot so that every comparison, subtraction, and calculation uses consistent timezone-aware datetimes. Ensure the bot correctly starts and manages rounds automatically without crashing.”

Tasks for Replit Agent:
	1.	Identify where datetime operations occur
Check all files that deal with rounds, timing, or scheduling (especially main.py).
Find all instances of datetime.now(), datetime.utcnow(), or datetime.fromtimestamp() used to calculate elapsed time or compare against round start times.
	2.	Standardize datetime usage
Replace all naive datetime calls with timezone-aware ones.
Import pytz or use zoneinfo if not already included.
Example correction:
now = datetime.now(pytz.utc)
Ensure all stored datetimes in the database or code also include UTC timezone.
If any timestamp is saved without timezone, convert it before subtracting:
if start_dt.tzinfo is None:
 start_dt = start_dt.replace(tzinfo=pytz.utc)
	3.	Fix the elapsed time calculation
Find the specific line (around line 2224 in main.py) where it says:
elapsed = (now - start_dt).total_seconds() / 60
Make sure both now and start_dt are timezone-aware before subtraction.
Confirm the fix by logging both values to verify they have UTC timezone.
	4.	Add Logging for Verification
Add print or logging lines to confirm correct datetime formats:
print(”[Round Manager] Now:”, now, “| Start_dt:”, start_dt)
	5.	Test the Fix
Run the bot and verify that no “offset-naive” errors appear.
Ensure rounds start and end correctly and that “Retrying in 30 seconds” loops stop appearing.
	6.	Ask for Environment Variables
Before running full tests, request all required environment variables in Replit Secrets to ensure nothing breaks after the datetime fix.
Ask the developer (me) for the following:
BOT_TOKEN
RPC_URL (Solana mainnet endpoint)
DB_PATH or database connection details
Any variables for wallet, admin, or payment verification functions.
	7.	Confirm Working State
After applying the fix and verifying environment variables, test at least two full rounds.
Ensure scheduler triggers automatically, no datetime errors appear, and round transitions are logged properly.

Expected Result:
The bot should manage rounds smoothly without datetime subtraction errors. All time calculations must be UTC-consistent, and the bot should handle automatic scheduling reliably.

