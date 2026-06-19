import sqlite3
import re

DB_PATH = "/home/pratik/nova/nova_projects.db"

FIELD_KEYWORDS = {
    "apis_used":      ["api", "fetch", "request", "http", "endpoint", "scrape", "crypto", "price"],
    "database_used":  ["database", "sqlite", "json", "csv", "storage", "store", "persist"],
    "bugs_found":     ["bug", "error", "fix", "crash", "fail", "import", "syntax"],
    "architecture":   ["cli", "web", "server", "multi", "thread", "async", "queue"],
    "performance":    ["speed", "token", "time", "fast", "slow", "concurrent"],
}

class ProjectDNA:
    def __init__(self):
        self.db_path = DB_PATH
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id   TEXT PRIMARY KEY,
                type         TEXT DEFAULT 'cli',
                architecture TEXT,
                apis_used    TEXT,
                database_used TEXT,
                deployment   TEXT,
                tags         TEXT,
                bugs_found   TEXT,
                fix_strategies TEXT,
                performance  TEXT,
                outcome      TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _execute(self, query, params=()):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        res = cursor.fetchall()
        conn.close()
        return res

    def _compress(self, value):
        """Truncate to 80 chars max — keeps it dense."""
        if not value:
            return ""
        value = str(value).strip()
        return value[:80] + "…" if len(value) > 80 else value

    def store(self, project_id, code, audit, topic, execution_valid,
              retry_count, time_taken, output_tokens):
        """Extract and store compressed DNA from completed run."""

        # Architecture: detect patterns from code
        arch_tags = []
        if "argparse" in code:    arch_tags.append("argparse")
        if "threading" in code:   arch_tags.append("threading")
        if "asyncio" in code:     arch_tags.append("asyncio")
        if "flask" in code.lower(): arch_tags.append("flask")
        if "fastapi" in code.lower(): arch_tags.append("fastapi")
        if "dispatch" in code or "dict" in code: arch_tags.append("dict-dispatch")
        architecture = self._compress("|".join(arch_tags) if arch_tags else "standard")

        # APIs used: detect from code
        api_tags = []
        if "requests" in code:     api_tags.append("requests")
        if "coingecko" in code.lower(): api_tags.append("coingecko")
        if "openai" in code.lower():    api_tags.append("openai")
        if "urllib" in code:       api_tags.append("urllib")
        apis_used = self._compress("|".join(api_tags) if api_tags else "none")

        # Database used
        db_tags = []
        if "sqlite3" in code:  db_tags.append("sqlite3")
        if "json" in code:     db_tags.append("json-file")
        if "csv" in code:      db_tags.append("csv")
        if "pickle" in code:   db_tags.append("pickle")
        database_used = self._compress("|".join(db_tags) if db_tags else "none")

        # Bugs: extract one-liners from audit
        bugs = []
        for line in audit.splitlines():
            line = line.strip()
            if any(k in line.lower() for k in ["bug", "error", "issue", "flaw", "missing", "risk"]):
                if 10 < len(line) < 120:
                    bugs.append(line[:80])
            if len(bugs) >= 3:
                break
        bugs_found = self._compress(" | ".join(bugs) if bugs else "none")

        # Fix strategies from audit
        fixes = []
        for line in audit.splitlines():
            line = line.strip()
            if any(k in line.lower() for k in ["fix", "recommend", "suggest", "should", "use", "add"]):
                if 10 < len(line) < 120:
                    fixes.append(line[:80])
            if len(fixes) >= 3:
                break
        fix_strategies = self._compress(" | ".join(fixes) if fixes else "none")

        # Performance: dense key-value
        lines = len(code.splitlines())
        performance = self._compress(
            f"lines:{lines}|time:{round(time_taken or 0, 1)}s|tokens:{output_tokens}|retries:{retry_count}"
        )
        tag_keywords = ["monitor", "alert", "threshold", "interval", "schedule",
                        "encrypt", "decrypt", "download", "upload", "scrape",
                        "parse", "convert", "track", "report", "export", "import",
                        "search", "filter", "sort", "compress", "watch", "log"]
        tags = "|".join(k for k in tag_keywords if k in topic.lower())
        tags = self._compress(tags if tags else "general")

        outcome = f"{'PASS' if execution_valid else 'FAIL'}|retries:{retry_count}"

        self._execute("""
            INSERT OR REPLACE INTO projects
            (project_id, type, architecture, apis_used, database_used,
             deployment, tags, bugs_found, fix_strategies, performance, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id, "cli", architecture, apis_used, database_used,
            "local-cli", tags, bugs_found, fix_strategies, performance, outcome
        ))

    def recall(self, topic):
        """
        Return a compressed, relevant DNA snippet for injection into coder prompt.
        Max 150 tokens. Only injects fields relevant to current task keywords.
        Threshold: overlap > 3 keywords.
        """
        words = set(re.findall(r'\w+', topic.lower()))
        important = [w for w in words if len(w) > 4]

        rows = self._execute("""
            SELECT project_id, architecture, apis_used, database_used,
                   tags, bugs_found, fix_strategies, performance, outcome
            FROM projects
        """)

        best = None
        best_score = 0

        for row in rows:
            proj_id, arch, apis, db, tags, bugs, fixes, perf, outcome = row
            combined = f"{arch} {apis} {db} {tags} {bugs} {fixes}".lower()
            score = sum(1 for w in important if w in combined)
            if score > best_score:
                best_score = score
                best = row

        if not best or best_score <= 3:
            return ""

        proj_id, arch, apis, db, tags, bugs, fixes, perf, outcome = best

        # Selectively include only relevant fields
        parts = []
        task_lower = topic.lower()

        if any(w in task_lower for w in FIELD_KEYWORDS["architecture"]):
            parts.append(f"arch:{arch}")
        if any(w in task_lower for w in FIELD_KEYWORDS["apis_used"]):
            parts.append(f"apis:{apis}")
        if any(w in task_lower for w in FIELD_KEYWORDS["database_used"]):
            parts.append(f"db:{db}")
        if any(w in task_lower for w in FIELD_KEYWORDS["bugs_found"]) or bugs != "none":
            parts.append(f"past_bugs:{bugs}")
        if fixes != "none":
            parts.append(f"fixes:{fixes}")
        parts.append(f"perf:{perf}|result:{outcome}")

        if not parts:
            return ""

        snippet = " | ".join(parts)
        # Hard cap: 150 tokens ≈ 600 chars
        if len(snippet) > 600:
            snippet = snippet[:597] + "…"

        return f"\n[PROJECT DNA — similar past project]\n{snippet}\n"
