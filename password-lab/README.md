# Password Lab — offline WordPress hash cracking (defensive education)

A self-contained, throwaway lab for *understanding* how a leaked WordPress
password database gets attacked — so you can defend against it. Everything
here operates on locally-generated, fake accounts. **Do not point any of this
at a live site you don't own and have written authorization to test.**

## Why it exists

WordPress stores passwords as salted, iterated **phpass** hashes
(`$P$...`). This lab demonstrates the one attack that matters once such a
hash leaks: an **offline dictionary attack**. The takeaway is visceral —
weak passwords fall in milliseconds, a long random one survives forever.

## Files

| File | Role | Hat |
|---|---|---|
| `wp_phpass.py` | Faithful, commented re-implementation of WordPress's phpass hasher (mint + verify). | the algorithm |
| `crosscheck.php` | WordPress's *canonical* phpass class; proves our Python is byte-for-byte compatible. | proof |
| `make_leak.py` | Generates `leaked_wp_users.csv` — fake users + real-format hashes. | victim |
| `crack.py` | Offline dictionary attack with cracker-style mangling rules. | attacker |
| `wordlist.txt` | Representative slice of common passwords (stands in for `rockyou.txt`). | ammunition |

## Run it

```bash
python3 wp_phpass.py        # self-test the hasher
python3 make_leak.py        # you get "breached" -> writes leaked_wp_users.csv
python3 crack.py            # you become the attacker -> cracks the weak ones
```

## Make it yours

Edit the `ACCOUNTS` list in `make_leak.py`, drop in passwords *you* actually
use, re-run, and watch how many guesses each survives. It's a brutally honest
strength meter.

## The lesson

- Hashing is a speed bump, not a vault — **password length/randomness** sets its height.
- "Complex" (`Summer2024!`) ≠ "strong"; crackers know human patterns.
- **Salting** defeats rainbow tables (forces per-account cracking).
- Real defense order: **patch plugins** (DB never leaks) → **long unique passwords** → **2FA**.
