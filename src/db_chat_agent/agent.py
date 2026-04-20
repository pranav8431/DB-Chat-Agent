from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.engine import Engine

from .config import Settings
from .db import get_schema_cached, infer_dialect, run_sql, validate_sql
from .llm import LLMClient
from .prompts import (
    ANSWER_SYSTEM_PROMPT,
    DIALECT_RULES_PROMPT,
    SQL_EXPLANATION_SYSTEM_PROMPT,
    SQL_SYSTEM_PROMPT,
)
from .profiler import profile_database


JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


class Memory:
    def __init__(self):
        self.history: list[tuple[str, str]] = []

    def add(self, question: str, sql: str) -> None:
        self.history.append((question, sql))

    def get_context(self, max_turns: int) -> str:
        recent = self.history[-max_turns:]
        return "\n".join([f"Q: {q}\nSQL: {s}" for q, s in recent])


class DatabaseChatAgent:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.settings = settings
        self.llm = LLMClient(settings)
        self.dialect = infer_dialect(engine)
        self.memory = Memory()
        db_uri = engine.url.render_as_string(hide_password=False)
        self.analysis: dict[str, Any] = {
            "schema": get_schema_cached(db_uri),
            "table_profiles": {},
        }

    def get_analysis(self) -> dict[str, Any]:
        if not self.analysis["table_profiles"]:
            self.analysis = profile_database(self.engine)
        return self.analysis

    def ask(self, question: str) -> dict[str, Any]:
        sql = self._generate_sql(question)
        query_result = run_sql(self.engine, sql, self.settings.max_result_rows)
        answer = self._generate_answer(question, sql, query_result)
        explanation = self._generate_sql_explanation(question, sql)
        self.memory.add(question, sql)
        return {
            "question": question,
            "sql": sql,
            "result": query_result,
            "answer": answer,
            "explanation": explanation,
        }

    def _schema_context(self, question: str) -> str:
        schema = self.analysis["schema"]
        relevant_tables = self._get_relevant_tables(question, schema)

        compact_schema: dict[str, Any] = {"tables": {}}
        for table_name in relevant_tables:
            table_meta = schema["tables"].get(table_name, {})
            columns = [c.get("name") for c in table_meta.get("columns", [])]
            compact_schema["tables"][table_name] = {
                "columns": columns,
                "primary_key": table_meta.get("primary_key", []),
                "foreign_keys": table_meta.get("foreign_keys", []),
            }

        return json.dumps(compact_schema, indent=2, default=str)

    def _get_relevant_tables(self, question: str, schema: dict[str, Any]) -> list[str]:
        question_lower = question.lower()
        table_names = list(schema.get("tables", {}).keys())
        matches: list[str] = []

        for table_name in table_names:
            if table_name.lower() in question_lower:
                matches.append(table_name)
                continue

            columns = schema["tables"][table_name].get("columns", [])
            if any(str(col.get("name", "")).lower() in question_lower for col in columns):
                matches.append(table_name)

        if matches:
            return matches[:8]

        return table_names[:6]

    def _generate_sql(self, question: str) -> str:
        schema_context = self._schema_context(question)
        memory_context = self.memory.get_context(self.settings.conversation_history_turns)
        system_prompt = (
            f"{SQL_SYSTEM_PROMPT}\n\n"
            f"{DIALECT_RULES_PROMPT.format(dialect=self.dialect)}"
        )

        retry_feedback = ""
        for _ in range(self.settings.sql_retry_attempts):
            user_prompt = (
                "DATABASE_SCHEMA:\n"
                f"{schema_context}\n\n"
                f"Previous context:\n{memory_context or 'None'}\n\n"
                f"Question: {question}\n"
                "Return JSON with SQL that answers the question.\n"
                f"{retry_feedback}"
            )
            model_text = self.llm.chat(
                system_prompt,
                user_prompt,
                temperature=0.35,
                max_tokens=self.settings.llm_max_tokens,
            )
            payload = self._extract_json(model_text)
            sql = (payload.get("sql") or "").strip()
            if sql and validate_sql(sql, self.dialect):
                return sql

            retry_feedback = "Fix the SQL. It was invalid for this dialect."

        raise ValueError("Failed to generate valid dialect-compatible SQL after retries.")

    def _generate_answer(self, question: str, sql: str, query_result: dict[str, Any]) -> str:
        result_json = json.dumps(query_result, indent=2, default=str)
        user_prompt = (
            f"Question: {question}\n"
            f"SQL used: {sql}\n"
            f"Result:\n{result_json}\n"
        )
        return self.llm.chat(
            ANSWER_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.4,
            max_tokens=self.settings.llm_max_tokens,
        )

    def _generate_sql_explanation(self, question: str, sql: str) -> str:
        prompt = (
            f"Question: {question}\n"
            f"SQL: {sql}\n"
            "Explain why this SQL matches the question."
        )
        try:
            return self.llm.chat(
                SQL_EXPLANATION_SYSTEM_PROMPT,
                prompt,
                temperature=0.4,
                max_tokens=140,
            )
        except Exception:
            return "The SQL was generated to match the question using schema-aware joins and filters."

    def _answer_schema_question(self, question: str) -> str:
        schema = self.analysis.get("schema", {}).get("tables", {})
        if not schema:
            return "No tables were found in the connected database."

        specific_table = self._resolve_table_name(question)
        if specific_table:
            table_meta = schema[specific_table]
            columns = table_meta.get("columns", [])
            column_desc = []
            for c in columns:
                name = str(c.get("name", ""))
                ctype = str(c.get("type", ""))
                nullable = "nullable" if c.get("nullable", True) else "not null"
                column_desc.append(f"- {name}: {ctype} ({nullable})")

            pk = table_meta.get("primary_key", [])
            fks = table_meta.get("foreign_keys", [])
            lines = [f"Schema for table '{specific_table}':"]
            lines.extend(column_desc or ["- No columns found"]) 
            lines.append(f"Primary key: {', '.join(pk) if pk else 'None'}")
            if fks:
                for fk in fks:
                    constrained = ", ".join(fk.get("constrained_columns", []))
                    referred = fk.get("referred_table")
                    referred_cols = ", ".join(fk.get("referred_columns", []))
                    lines.append(
                        f"Foreign key: ({constrained}) -> {referred}({referred_cols})"
                    )
            else:
                lines.append("Foreign key: None")
            return "\n".join(lines)

        lines = ["Tables in the connected database:"]
        for table_name in sorted(schema.keys()):
            columns = schema[table_name].get("columns", [])
            col_names = [str(c.get("name", "")) for c in columns][:8]
            preview = ", ".join([c for c in col_names if c])
            if preview:
                lines.append(f"- {table_name}: {preview}")
            else:
                lines.append(f"- {table_name}")

        return "\n".join(lines)

    def _answer_row_request(self, limit: int, requested_table: str | None) -> dict[str, Any] | None:
        schema_tables = self.analysis.get("schema", {}).get("tables", {})
        table_names = list(schema_tables.keys())
        if not table_names:
            return {
                "question": f"first {limit} rows",
                "sql": None,
                "result": None,
                "answer": "No tables were found in the connected database.",
                "explanation": "Row preview skipped because schema has no tables.",
            }

        selected_table = requested_table
        if not selected_table:
            if len(table_names) == 1:
                selected_table = table_names[0]
            else:
                available = ", ".join(sorted(table_names)[:8])
                return {
                    "question": f"first {limit} rows",
                    "sql": None,
                    "result": None,
                    "answer": (
                        "I can show first rows, but please specify the table name. "
                        f"Available tables include: {available}"
                    ),
                    "explanation": "Clarification requested because multiple tables exist.",
                }

        columns = schema_tables[selected_table].get("columns", [])
        column_names = [str(c.get("name", "")) for c in columns if c.get("name")]
        if not column_names:
            return {
                "question": f"first {limit} rows of {selected_table}",
                "sql": None,
                "result": None,
                "answer": f"Table '{selected_table}' has no columns to query.",
                "explanation": "Table metadata did not include column names.",
            }

        safe_table = self._safe_identifier(selected_table)
        projected_cols = ", ".join([self._safe_identifier(c) for c in column_names])
        sql = f"SELECT {projected_cols} FROM {safe_table} LIMIT {limit}"
        query_result = run_sql(self.engine, sql, self.settings.max_result_rows)
        answer = f"Showing first {query_result['row_count']} rows from table '{selected_table}'."
        return {
            "question": f"first {limit} rows of {selected_table}",
            "sql": sql,
            "result": query_result,
            "answer": answer,
            "explanation": "Executed deterministic row preview query for requested table.",
        }

    def _resolve_table_name(self, question: str) -> str | None:
        lowered = question.lower()
        table_names = list(self.analysis.get("schema", {}).get("tables", {}).keys())
        for table in table_names:
            t = table.lower()
            if re.search(rf"\b{re.escape(t)}\b", lowered):
                return table
            if t.endswith("s") and re.search(rf"\b{re.escape(t[:-1])}\b", lowered):
                return table
        return None

    @staticmethod
    def _safe_identifier(identifier: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
            raise ValueError(f"Unsafe identifier detected: {identifier}")
        return identifier

    def _extract_row_request(self, question: str) -> tuple[int, str | None] | None:
        lowered = question.lower()
        if not re.search(r"\b(row|rows)\b", lowered):
            return None

        match = re.search(r"\b(first|top)\s+(\d+)\s+rows?\b", lowered)
        if not match:
            return None

        limit = max(1, min(int(match.group(2)), self.settings.max_result_rows))
        table_name = self._resolve_table_name(question)
        return limit, table_name

    @staticmethod
    def _is_ambiguous(question: str) -> bool:
        lowered = question.lower()
        if DatabaseChatAgent._is_schema_question(question):
            return False

        # Match vague words as standalone tokens to avoid false positives
        # like "database" matching "data".
        return re.search(r"\b(performance|data|details)\b", lowered) is not None

    @staticmethod
    def _is_schema_question(question: str) -> bool:
        lowered = question.lower()
        schema_patterns = [
            r"\bschema\b",
            r"\btable(s)?\b",
            r"\bcolumn(s)?\b",
            r"\bwhat\s+tables\b",
            r"\blist\s+tables\b",
            r"\bdescribe\s+database\b",
            r"\bstructure\b",
        ]
        return any(re.search(pattern, lowered) for pattern in schema_patterns)

    @staticmethod
    def _clarification_prompt(question: str) -> str:
        return (
            f"The request '{question}' is ambiguous. Do you mean:\n"
            "1. Revenue performance\n"
            "2. User activity\n"
            "3. Order trends"
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except Exception:
            match = JSON_BLOCK_RE.search(text)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return {"sql": None}
            return {"sql": None}
