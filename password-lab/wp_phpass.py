"""
wp_phpass.py — a faithful re-implementation of WordPress's password hasher.

WordPress stores passwords in the `wp_users.user_pass` column using "phpass"
(Portable PHP password hashing). A stored hash looks like:

    $P$B7Tns9F0e8sX5kq2mGZ0c4Yd1u9aR1.

  $P$        -> identifies the portable phpass algorithm
     B        -> log2(iterations). 'B' = index 11 -> 2^11 = 2048 MD5 rounds
      7Tns9F0e  -> 8-character salt
              <22 chars>  -> the actual hash, in phpass's custom base64

The KEY security idea is in here: it's *salted* (so two users with the same
password get different hashes -> rainbow tables are useless) and *iterated*
(thousands of MD5 rounds -> each guess is deliberately slow).

This file is used both to MINT hashes (acting as WordPress) and to VERIFY a
guess (acting as the attacker's cracker). Same code, two hats.
"""

import hashlib
import os

ITOA64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def _encode64(data: bytes, count: int) -> str:
    """phpass's custom base64 — not standard base64, this exact variant."""
    out = []
    i = 0
    while i < count:
        value = data[i]
        i += 1
        out.append(ITOA64[value & 0x3f])
        if i < count:
            value |= data[i] << 8
        out.append(ITOA64[(value >> 6) & 0x3f])
        if i >= count:
            break
        i += 1
        if i < count:
            value |= data[i] << 16
        out.append(ITOA64[(value >> 12) & 0x3f])
        if i >= count:
            break
        i += 1
        out.append(ITOA64[(value >> 18) & 0x3f])
    return ''.join(out)


def crypt_private(password: str, setting: str) -> str:
    """
    The core phpass routine. Given a password and a `setting` string
    ($P$ + cost char + 8-char salt), produce the full hash.

    To verify a password you call this with the stored hash AS the setting
    (the first 12 chars carry the algorithm/cost/salt) and compare.
    """
    if setting[:3] != '$P$' and setting[:3] != '$H$':
        return '*0'  # unsupported -> never matches

    count_log2 = ITOA64.index(setting[3])
    count = 1 << count_log2          # e.g. 2^11 = 2048 iterations
    salt = setting[4:12]
    if len(salt) != 8:
        return '*0'

    pw = password.encode('utf-8')
    h = hashlib.md5((salt + password).encode('utf-8')).digest()
    for _ in range(count):
        h = hashlib.md5(h + pw).digest()  # iterate -> deliberately slow

    return setting[:12] + _encode64(h, 16)


def make_hash(password: str, iterations_log2: int = 11) -> str:
    """Act as WordPress: create a fresh salted hash for a new password."""
    salt = _encode64(os.urandom(6), 6)[:8]  # 6 random bytes -> 8 base64 chars
    setting = '$P$' + ITOA64[iterations_log2] + salt
    return crypt_private(password, setting)


def verify(password: str, stored_hash: str) -> bool:
    """Act as the login check (and the attacker's oracle)."""
    return crypt_private(password, stored_hash) == stored_hash


if __name__ == '__main__':
    # quick self-test: prove minting + verifying round-trips, and that
    # the same password yields DIFFERENT hashes (salting at work).
    h1 = make_hash('hunter2')
    h2 = make_hash('hunter2')
    print('hash #1:', h1)
    print('hash #2:', h2)
    print('different hashes, same password? ->', h1 != h2)
    print('verify correct password ->', verify('hunter2', h1))
    print('verify wrong   password ->', verify('hunter3', h1))
