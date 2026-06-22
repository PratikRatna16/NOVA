#!/usr/bin/env python3
import argparse
import sqlite3
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
import shutil

DB_PATH = Path.home() / ".flashcards.db"

# ANSI colors
COLORS = {
    'reset': '\033[0m',
    'green': '\033[92m',
    'red': '\033[91m',
    'yellow': '\033[93m',
    'blue': '\033[94m',
    'cyan': '\033[96m',
    'bold': '\033[1m'
}

def colorize(text, color):
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS flashcards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        difficulty TEXT DEFAULT 'medium',
        category TEXT DEFAULT 'general',
        ease_factor REAL DEFAULT 2.5,
        interval INTEGER DEFAULT 1,
        repetitions INTEGER DEFAULT 0,
        next_review DATE
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flashcard_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        correct INTEGER,
        response_time REAL,
        FOREIGN KEY (flashcard_id) REFERENCES flashcards(id)
    )''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def add_flashcard(question, answer, difficulty, category):
    conn = get_db()
    c = conn.cursor()
    next_review = datetime.now().date() + timedelta(days=1)
    c.execute('INSERT INTO flashcards (question, answer, difficulty, category, next_review) VALUES (?, ?, ?, ?, ?)',
              (question, answer, difficulty, category, next_review))
    conn.commit()
    conn.close()
    print(colorize(f"Added flashcard: {question[:40]}...", 'green'))

def edit_flashcard(card_id, field, value):
    conn = get_db()
    c = conn.cursor()
    c.execute(f'UPDATE flashcards SET {field} = ? WHERE id = ?', (value, card_id))
    if c.rowcount == 0:
        print(colorize(f"No flashcard found with ID {card_id}", 'red'))
    else:
        print(colorize(f"Updated {field} for card {card_id}", 'green'))
    conn.commit()
    conn.close()

def delete_flashcard(card_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM flashcards WHERE id = ?', (card_id,))
    if c.rowcount == 0:
        print(colorize(f"No flashcard found with ID {card_id}", 'red'))
    else:
        print(colorize(f"Deleted flashcard {card_id}", 'green'))
    conn.commit()
    conn.close()

def get_due_cards(category=None):
    conn = get_db()
    c = conn.cursor()
    today = datetime.now().date()
    if category:
        c.execute('SELECT * FROM flashcards WHERE next_review <= ? AND category = ?', (today, category))
    else:
        c.execute('SELECT * FROM flashcards WHERE next_review <= ?', (today,))
    cards = c.fetchall()
    conn.close()
    return cards

def get_all_cards():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM flashcards')
    cards = c.fetchall()
    conn.close()
    return cards

def update_spaced_repetition(card_id, quality):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM flashcards WHERE id = ?', (card_id,))
    card = c.fetchone()
    if not card:
        conn.close()
        return
    
    # SuperMemo-2 inspired algorithm
    ease = card['ease_factor']
    interval = card['interval']
    reps = card['repetitions']
    
    if quality < 3:  # Incorrect
        reps = 0
        interval = 1
    else:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            interval = int(interval * ease)
    
    ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    next_review = datetime.now().date() + timedelta(days=interval)
    
    c.execute('UPDATE flashcards SET ease_factor = ?, interval = ?, repetitions = ?, next_review = ? WHERE id = ?',
              (ease, interval, reps, next_review, card_id))
    
    c.execute('INSERT INTO reviews (flashcard_id, correct, response_time) VALUES (?, ?, ?)',
              (card_id, 1 if quality >= 3 else 0, 0))
    conn.commit()
    conn.close()

def get_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as total FROM flashcards')
    total = c.fetchone()['total']
    c.execute('SELECT AVG(correct) as pct, AVG(response_time) as avg_time FROM reviews')
    stats = c.fetchone()
    c.execute('SELECT COUNT(*) FROM flashcards WHERE next_review <= ?', (datetime.now().date(),))
    due = c.fetchone()[0]
    conn.close()
    return {'total': total, 'accuracy': (stats['pct'] or 0) * 100, 'avg_time': stats['avg_time'] or 0, 'due': due}

def review_cards(category=None):
    cards = get_due_cards(category)
    if not cards:
        print(colorize("No cards due for review!", 'yellow'))
        return
    
    random.shuffle(cards)
    for card in cards:
        terminal_width = shutil.get_terminal_size().columns
        print("\n" + "=" * terminal_width)
        print(colorize(f"Category: {card['category']} | Difficulty: {card['difficulty']}", 'cyan'))
        print("=" * terminal_width)
        print(colorize(f"Q: {card['question']}", 'bold'))
        
        input("Press Enter to see answer...")
        print(colorize(f"A: {card['answer']}", 'blue'))
        
        start = time.time()
        quality = 0
        while quality not in range(1, 6):
            try:
                quality = int(input(f"\nRate (1=Fail, 2=Hard, 3=Good, 4=Easy): "))
                if quality not in range(1, 6):
                    print(colorize("Please enter 1-5", 'red'))
            except ValueError:
                print(colorize("Invalid input", 'red'))
        
        update_spaced_repetition(card['id'], quality)

def list_cards(category=None):
    cards = get_all_cards()
    if category:
        cards = [c for c in cards if c['category'] == category]
    
    if not cards:
        print(colorize("No flashcards found.", 'yellow'))
        return
    
    terminal_width = shutil.get_terminal_size().columns
    print(f"\n{'ID':<5} {'Question':<40} {'Category':<15} {'Due':<12}")
    print("-" * terminal_width)
    
    for card in cards:
        due = "Yes" if card['next_review'] <= datetime.now().date() else "No"
        print(f"{card['id']:<5} {card['question'][:40]:<40} {card['category']:<15} {due:<12}")

def main():
    init_db()
    parser = argparse.ArgumentParser(description="CLI Flashcard App with Spaced Repetition")
    subparsers = parser.add_subparsers(dest='command')
    
    # Add command
    add_parser = subparsers.add_parser('add')
    add_parser.add_argument('question')
    add_parser.add_argument('answer')
    add_parser.add_argument('--difficulty', '-d', choices=['easy', 'medium', 'hard'], default='medium')
    add_parser.add_argument('--category', '-c', default='general')
    
    # Edit command
    edit_parser = subparsers.add_parser('edit')
    edit_parser.add_argument('card_id', type=int)
    edit_parser.add_argument('field', choices=['question', 'answer', 'difficulty', 'category'])
    edit_parser.add_argument('value')
    
    # Delete command
    del_parser = subparsers.add_parser('delete')
    del_parser.add_argument('card_id', type=int)
    
    # Review command
    rev_parser = subparsers.add_parser('review')
    rev_parser.add_argument('--category', '-c')
    
    # List command
    list_parser = subparsers.add_parser('list')
    list_parser.add_argument('--category', '-c')
    
    # Stats command
    subparsers.add_parser('stats')
    
    args = parser.parse_args()
    commands = {
        'add': lambda: add_flashcard(args.question, args.answer, args.difficulty, args.category),
        'edit': lambda: edit_flashcard(args.card_id, args.field, args.value),
        'delete': lambda: delete_flashcard(args.card_id),
        'review': lambda: review_cards(args.category),
        'list': lambda: list_cards(args.category),
        'stats': lambda: print_stats()
    }
    
    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()

def print_stats():
    stats = get_stats()
    print(f"\nTotal cards: {stats['total']}")
    print(f"Cards due: {stats['due']}")
    print(f"Overall accuracy: {stats['accuracy']:.1f}%")
    print(f"Average response time: {stats['avg_time']:.2f}s")

if __name__ == '__main__':
    main()