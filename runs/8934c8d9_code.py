#!/usr/bin/env python3
import secrets
import string
import math
import argparse
import sqlite3
import os
import hashlib
import base64
from cryptography.fernet import Fernet
from collections import Counter

DB_PATH = os.path.expanduser("~/.pwman.db")
MAX_RETRIES = 3
CHARSETS = {
    'alphanumeric': string.ascii_letters + string.digits,
    'lowercase': string.ascii_lowercase,
    'uppercase': string.ascii_uppercase,
    'digits': string.digits,
    'special': string.punctuation,
    'all': string.ascii_letters + string.digits + string.punctuation,
    'hex': '0123456789abcdef'
}

def generate_password(length=16, charset='alphanumeric'):
    if length <= 0:
        raise ValueError("Password length must be positive")
    chars = CHARSETS.get(charset, CHARSETS['alphanumeric'])
    if not chars:
        raise ValueError(f"Unknown charset: {charset}")
    return ''.join(secrets.choice(chars) for _ in range(length))

def calculate_entropy(password, charset='alphanumeric'):
    chars = CHARSETS.get(charset, CHARSETS['alphanumeric'])
    n = len(chars)
    if n == 0:
        return 0
    freq = Counter(password)
    entropy = -sum((count / len(password)) * math.log2(count / len(password)) 
                   for count in freq.values())
    return entropy

def derive_key(master_password, salt=b'pwman_v1_salt'):
    key = hashlib.pbkdf2_hmac('sha256', master_password.encode(), salt, 100000)
    return base64.urlsafe_b64encode(key)

def encrypt_with_retry(password, key, max_retries=MAX_RETRIES):
    for _ in range(max_retries):
        try:
            f = Fernet(key)
            return f.encrypt(password.encode())
        except Exception:
            continue
    raise RuntimeError("Encryption failed after retries")

def decrypt_with_retry(encrypted, key, max_retries=MAX_RETRIES):
    for _ in range(max_retries):
        try:
            f = Fernet(key)
            return f.decrypt(encrypted).decode()
        except Exception:
            continue
    raise RuntimeError("Decryption failed after retries")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS passwords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service TEXT UNIQUE NOT NULL,
        encrypted TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def store_password(service, password, master_key):
    conn = sqlite3.connect(DB_PATH)
    try:
        encrypted = encrypt_with_retry(password, master_key)
        conn.execute('INSERT OR REPLACE INTO passwords (service, encrypted) VALUES (?, ?)',
                     (service, encrypted.decode()))
        conn.commit()
    finally:
        conn.close()

def retrieve_password(service, master_key):
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute('SELECT encrypted FROM passwords WHERE service = ?', (service,))
        if (row := cursor.fetchone()) and row[0]:
            return decrypt_with_retry(row[0].encode(), master_key)
        return None
    finally:
        conn.close()

def list_services():
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute('SELECT service, created_at FROM passwords ORDER BY created_at DESC')
        return cursor.fetchall()
    finally:
        conn.close()

def delete_password(service):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('DELETE FROM passwords WHERE service = ?', (service,))
        conn.commit()
        return cursor.rowcount if (cursor := conn.execute('SELECT changes()')) else 0
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description='Password Generator and Manager',
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-g', '--generate', action='store_true', help='Generate password')
    parser.add_argument('-r', '--retrieve', action='store_true', help='Retrieve password')
    parser.add_argument('-l', '--length', type=int, default=16, help='Password length')
    parser.add_argument('-c', '--charset', choices=list(CHARSETS.keys()), 
                        default='alphanumeric', help='Character set')
    parser.add_argument('-s', '--service', help='Service name')
    parser.add_argument('-m', '--master-password', help='Master password for encryption')
    parser.add_argument('-L', '--list', action='store_true', help='List stored services')
    parser.add_argument('-d', '--delete', help='Delete password for service')
    parser.add_argument('--show', action='store_true', help='Show password in output (default: masked)')

    args = parser.parse_args()
    
    if args.list:
        init_db()
        for service, created in list_services():
            print(f"{service}: {created}")
    elif args.delete:
        init_db()
        delete_password(args.delete)
        print(f"Deleted password for: {args.delete}")
    elif args.generate:
        if args.length <= 0:
            parser.error("Length must be positive")
        password = generate_password(args.length, args.charset)
        entropy = calculate_entropy(password, args.charset)
        print(password if args.show else f"{'*' * len(password)} (entropy: {entropy:.1f} bits)")
        if args.service and args.master_password:
            init_db()
            store_password(args.service, password, derive_key(args.master_password))
            print(f"Stored password for: {args.service}")
    elif args.retrieve:
        if not args.service or not args.master_password:
            parser.error("--service and --master-password required for retrieval")
        init_db()
        result = retrieve_password(args.service, derive_key(args.master_password))
        if result:
            print(result if args.show else f"{'*' * len(result)}")
        else:
            print(f"No password found for: {args.service}")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()