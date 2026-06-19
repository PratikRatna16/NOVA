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
                content TEXT,
                run_id TEXT
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

    def _add_node(self, node_id, node_type, content, run_id):
        self._execute(
            "INSERT OR REPLACE INTO graph_nodes VALUES (?, ?, ?, ?)",
            (node_id, node_type, content, run_id)
        )

    def _add_edge(self, source, target, relationship):
        self._execute(
            "INSERT OR IGNORE INTO graph_edges VALUES (?, ?, ?)",
            (source, target, relationship)
        )

    def remember_experience(self, run_id, task_prompt, error_text=None, fix_text=None,
                             goal=None, files_created=None, deployment=None, outcome=None):
        """Builds the full structural experience tree for the execution run."""
        task_node_id = f"task_{run_id}"
        self._add_node(task_node_id, "task", task_prompt, run_id)

        if goal:
            goal_node_id = f"goal_{run_id}"
            self._add_node(goal_node_id, "goal", goal, run_id)
            self._add_edge(task_node_id, goal_node_id, "HAS_GOAL")

        if files_created:
            files_node_id = f"files_{run_id}"
            self._add_node(files_node_id, "files", files_created, run_id)
            self._add_edge(task_node_id, files_node_id, "CREATED")

        if deployment:
            deploy_node_id = f"deploy_{run_id}"
            self._add_node(deploy_node_id, "deployment", deployment, run_id)
            self._add_edge(task_node_id, deploy_node_id, "DEPLOYED_AS")

        if outcome:
            outcome_node_id = f"outcome_{run_id}"
            self._add_node(outcome_node_id, "outcome", outcome, run_id)
            self._add_edge(task_node_id, outcome_node_id, "RESULTED_IN")

        if error_text and error_text.strip():
            error_node_id = f"err_{run_id}"
            clean_err = error_text.strip().split('\n')[-1]
            self._add_node(error_node_id, "error", clean_err, run_id)
            self._add_edge(task_node_id, error_node_id, "ENCOUNTERED")

            if fix_text and fix_text.strip():
                fix_node_id = f"fix_{run_id}"
                self._add_node(fix_node_id, "fix", fix_text.strip(), run_id)
                self._add_edge(error_node_id, fix_node_id, "RESOLVED_BY")

    def recall_experience(self, new_task_prompt):
        """Scans the graph for similar previous tasks and pulls connected experience nodes"""
        words = re.findall(r'\w+', new_task_prompt.lower())
        important_words = [w for w in words if len(w) > 4]
        all_tasks = self._execute("SELECT id, content FROM graph_nodes WHERE type='task'")

        best_match_id = None
        max_overlap = 0
        for task_id, content in all_tasks:
            overlap = sum(1 for word in important_words if word in content.lower())
            if overlap > max_overlap:
                max_overlap = overlap
                best_match_id = task_id

        if not best_match_id or max_overlap < 2:
            return ""

        context_parts = []

        outcome_row = self._execute(
            "SELECT n.content FROM graph_edges e JOIN graph_nodes n ON e.target = n.id "
            "WHERE e.source = ? AND e.relationship = 'RESULTED_IN'",
            (best_match_id,)
        )
        if outcome_row:
            context_parts.append(f"- Previous similar task outcome: {outcome_row[0][0]}")

        fix_query = """
            SELECT e.content, f.content
            FROM graph_edges e_edge
            JOIN graph_nodes e ON e_edge.target = e.id
            JOIN graph_edges f_edge ON f_edge.source = e.id
            JOIN graph_nodes f ON f_edge.target = f.id
            WHERE e_edge.source = ? AND e_edge.relationship = 'ENCOUNTERED' AND f_edge.relationship = 'RESOLVED_BY'
        """
        fix_results = self._execute(fix_query, (best_match_id,))
        if fix_results:
            err, fix = fix_results[0]
            context_parts.append(f"- Historical block encountered: {err}")
            context_parts.append(f"- Verified resolution strategy: {fix}")

        if not context_parts:
            return ""

        return "\n[PAST EXPERIENCE CONTEXT FOUND]\n" + "\n".join(context_parts) + "\n"
