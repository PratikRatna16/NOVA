import sqlite3
import re

DB_PATH = "/home/pratik/nova/nova_runs.db"

class ExperienceGraph:
    def __init__(self):
        self.db_path = DB_PATH
        self._execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                type TEXT,
                content TEXT
            )
        """)
        self._execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                source TEXT,
                target TEXT,
                relationship TEXT,
                PRIMARY KEY (source, target, relationship)
            )
        """)

    def _execute(self, query, params=()):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        res = cursor.fetchall()
        conn.close()
        return res

    def remember_experience(self, run_id, task_prompt, error_text=None, fix_text=None):
        """Builds a mini structural graph for the execution run"""
        # 1. Insert Task Node
        task_node_id = f"task_{run_id}"
        self._execute("INSERT OR REPLACE INTO graph_nodes VALUES (?, ?, ?)", (task_node_id, "task", task_prompt))

        # 2. If there was a failure, build out the error and fix nodes/edges
        if error_text and error_text.strip():
            error_node_id = f"err_{run_id}"
            # Extract just the main error line to keep it dense
            clean_err = error_text.strip().split('\n')[-1]
            self._execute("INSERT OR REPLACE INTO graph_nodes VALUES (?, ?, ?)", (error_node_id, "error", clean_err))
            
            # Connect Task -> Encountered -> Error
            self._execute("INSERT OR IGNORE INTO graph_edges VALUES (?, ?, ?)", (task_node_id, error_node_id, "ENCOUNTERED"))

            if fix_text and fix_text.strip():
                fix_node_id = f"fix_{run_id}"
                self._execute("INSERT OR REPLACE INTO graph_nodes VALUES (?, ?, ?)", (fix_node_id, "fix", fix_text.strip()))
                
                # Connect Error -> Resolved By -> Fix
                self._execute("INSERT OR IGNORE INTO graph_edges VALUES (?, ?, ?)", (error_node_id, fix_node_id, "RESOLVED_BY"))

    def recall_experience(self, new_task_prompt):
        """Scans the graph for similar previous tasks and pulls connected friction nodes"""
        # Simple, robust keyword overlapping to identify historical project similarities
        words = re.findall(r'\w+', new_task_prompt.lower())
        important_words = [w for w in words if len(w) > 4] # target specific words like 'scraper', 'organizer', 'watchdog'

        all_tasks = self._execute("SELECT id, content FROM graph_nodes WHERE type='task'")
        
        best_match_id = None
        max_overlap = 0

        for task_id, content in all_tasks:
            overlap = sum(1 for word in important_words if word in content.lower())
            if overlap > max_overlap:
                max_overlap = overlap
                best_match_id = task_id

        if not best_match_id or max_overlap < 2:
            return "" # No highly relevant patterns found

        # Traverse graph paths if an error pattern exists: Task -> Error -> Fix
        query = """
            SELECT e.content, f.content 
            FROM graph_edges e_edge
            JOIN graph_nodes e ON e_edge.target = e.id
            JOIN graph_edges f_edge ON f_edge.source = e.id
            JOIN graph_nodes f ON f_edge.target = f.id
            WHERE e_edge.source = ? AND e_edge.relationship = 'ENCOUNTERED' AND f_edge.relationship = 'RESOLVED_BY'
        """
        results = self._execute(query, (best_match_id,))

        if results:
            err, fix = results[0]
            return f"\n[PAST EXPERIENCE CONTEXT FOUND]\n- Historical block encountered: {err}\n- Verified resolution strategy: {fix}\n"
        
        return ""
