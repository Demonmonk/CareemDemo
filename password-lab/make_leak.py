"""
make_leak.py — VICTIM SIDE.

Simulates what an attacker walks away with after dumping your `wp_users`
table (e.g. via a SQL-injection in some vulnerable plugin). They never see
plaintext passwords — only username + salted phpass hash.

We seed four accounts spanning the realistic spectrum, from "password is in
every wordlist" to "16 random chars". Then we hand the attacker ONLY the
hashes. The whole point: which of these can they reverse, and how fast?
"""

import csv
import wp_phpass

# (username, the secret password — known only to us, the victim)
ACCOUNTS = [
    ('user1',      'password123'),       # textbook weak — top of every list
    ('editor_sam', 'Summer2024!'),       # "looks strong", but it's a known pattern
    ('shop_admin', 'shlguru'),           # site name as password — attackers try this
    ('owner',      'pK7$vR2!mQ9wZ4xL'),  # 16 random chars — the control case
]

with open('leaked_wp_users.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['user_login', 'user_pass'])  # same columns as the real table
    for username, password in ACCOUNTS:
        w.writerow([username, wp_phpass.make_hash(password)])

print('Wrote leaked_wp_users.csv — this is all the attacker gets:\n')
with open('leaked_wp_users.csv') as f:
    print(f.read())
