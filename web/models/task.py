"""
任务数据模型

定义任务相关的数据结构和操作
"""

import logging
import os
import sqlite3
from enum import Enum
from typing import List, Optional

import time

logger = logging.getLogger(__name__)

# 数据库文件路径
DATABASE_FILE = os.path.join(os.path.dirname(__file__), "..", "data.db")


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    """任务模型"""

    def __init__(
        self,
        task_id: str,
        source_type: str,
        path: str,
        write_mode: str,
        space_name: Optional[str] = None,
        branch: Optional[str] = None,
        commit_hash: Optional[str] = None,
        max_workers: int = 2,
        chunk_workers: int = 4,
        notify_level: str = "normal",
        dry_run: bool = False
    ):
        self.task_id = task_id
        self.source_type = source_type
        self.path = path
        self.write_mode = write_mode
        self.space_name = space_name
        self.branch = branch
        self.commit_hash = commit_hash
        self.max_workers = max_workers
        self.chunk_workers = chunk_workers
        self.notify_level = notify_level
        self.dry_run = dry_run
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.message = ""
        self.total = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.failures: List[str] = []
        self.skipped_items: List[str] = []
        self.created_docs: List[str] = []
        self.start_time = None
        self.end_time = None

    @classmethod
    def _get_connection(cls):
        """获取数据库连接"""
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def _create_table(cls):
        """创建任务表"""
        conn = cls._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                source_type TEXT,
                path TEXT,
                write_mode TEXT,
                space_name TEXT,
                branch TEXT,
                commit_hash TEXT,
                max_workers INTEGER,
                chunk_workers INTEGER,
                notify_level TEXT,
                dry_run BOOLEAN,
                status TEXT,
                progress INTEGER,
                message TEXT,
                total INTEGER,
                success INTEGER,
                failed INTEGER,
                skipped INTEGER,
                failures TEXT,
                skipped_items TEXT,
                created_docs TEXT,
                start_time REAL,
                end_time REAL
            )
        """)

        conn.commit()
        conn.close()

    @classmethod
    def create_from_task(cls, task):
        """从现有任务创建新任务"""
        new_task = cls(
            task_id = str(time.time()),
            source_type = task.source_type,
            path = task.path,
            write_mode = task.write_mode,
            space_name = task.space_name,
            branch = task.branch,
            commit_hash = task.commit_hash,
            max_workers = task.max_workers,
            chunk_workers = task.chunk_workers,
            notify_level = task.notify_level,
            dry_run = task.dry_run
        )
        new_task.save()
        return new_task.task_id

    def save(self):
        """保存任务到数据库"""
        self._create_table()

        conn = self._get_connection()
        cursor = conn.cursor()

        # 序列化列表字段
        failures_str = ";".join(self.failures)
        skipped_items_str = ";".join(self.skipped_items)
        created_docs_str = ";".join(self.created_docs)

        cursor.execute("""
            REPLACE INTO tasks (
                task_id, source_type, path, write_mode, space_name, branch, commit_hash,
                max_workers, chunk_workers, notify_level, dry_run, status, progress,
                message, total, success, failed, skipped, failures, skipped_items,
                created_docs, start_time, end_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.task_id, self.source_type, self.path, self.write_mode, self.space_name,
            self.branch, self.commit_hash, self.max_workers, self.chunk_workers,
            self.notify_level, self.dry_run, self.status, self.progress, self.message,
            self.total, self.success, self.failed, self.skipped, failures_str,
            skipped_items_str, created_docs_str, self.start_time, self.end_time
        ))

        conn.commit()
        conn.close()

    @classmethod
    def get(cls, task_id: str):
        """根据ID获取任务"""
        cls._create_table()

        conn = cls._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()

        if row:
            task = cls(
                task_id = row["task_id"],
                source_type = row["source_type"],
                path = row["path"],
                write_mode = row["write_mode"],
                space_name = row["space_name"],
                branch = row["branch"],
                commit_hash = row["commit_hash"],
                max_workers = row["max_workers"],
                chunk_workers = row["chunk_workers"],
                notify_level = row["notify_level"],
                dry_run = row["dry_run"]
            )

            task.status = row["status"]
            task.progress = row["progress"]
            task.message = row["message"]
            task.total = row["total"]
            task.success = row["success"]
            task.failed = row["failed"]
            task.skipped = row["skipped"]

            # 反序列化列表字段
            if row["failures"]:
                task.failures = row["failures"].split(";")
            if row["skipped_items"]:
                task.skipped_items = row["skipped_items"].split(";")
            if row["created_docs"]:
                task.created_docs = row["created_docs"].split(";")

            task.start_time = row["start_time"]
            task.end_time = row["end_time"]

            conn.close()
            return task

        conn.close()
        return None

    @classmethod
    def get_all(cls):
        """获取所有任务"""
        cls._create_table()

        conn = cls._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM tasks ORDER BY start_time DESC")
        rows = cursor.fetchall()

        tasks = []
        for row in rows:
            task = cls(
                task_id = row["task_id"],
                source_type = row["source_type"],
                path = row["path"],
                write_mode = row["write_mode"],
                space_name = row["space_name"],
                branch = row["branch"],
                commit = row["commit"],
                max_workers = row["max_workers"],
                chunk_workers = row["chunk_workers"],
                notify_level = row["notify_level"],
                dry_run = row["dry_run"]
            )

            task.status = row["status"]
            task.progress = row["progress"]
            task.message = row["message"]
            task.total = row["total"]
            task.success = row["success"]
            task.failed = row["failed"]
            task.skipped = row["skipped"]

            if row["failures"]:
                task.failures = row["failures"].split(";")
            if row["skipped_items"]:
                task.skipped_items = row["skipped_items"].split(";")
            if row["created_docs"]:
                task.created_docs = row["created_docs"].split(";")

            task.start_time = row["start_time"]
            task.end_time = row["end_time"]

            tasks.append(task)

        conn.close()
        return tasks

    @classmethod
    def delete(cls, task_id: str):
        """删除任务"""
        cls._create_table()

        conn = cls._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()
        conn.close()
