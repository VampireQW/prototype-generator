# -*- coding: utf-8 -*-
"""
SQLite 数据库层
- 用户、团队、项目归属、分享
- WAL 模式支持并发读
"""

import sqlite3
import os
import secrets
import datetime
import hashlib
import threading

DB_FILE = os.path.join('data', 'collab.db')

# 线程本地存储，每个线程独立连接
_local = threading.local()


def get_conn():
    """获取当前线程的数据库连接"""
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_FILE, timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    """初始化数据库表"""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            invite_code TEXT UNIQUE NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TEXT NOT NULL,
            PRIMARY KEY (team_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS project_ownership (
            project_id TEXT PRIMARY KEY,
            owner_id INTEGER NOT NULL REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS project_shares (
            project_id TEXT NOT NULL,
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            shared_by INTEGER NOT NULL REFERENCES users(id),
            shared_at TEXT NOT NULL,
            PRIMARY KEY (project_id, team_id)
        );
    """)
    conn.commit()


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ==================== 密码哈希 ====================
# 使用 hashlib (PBKDF2) 避免安装 bcrypt 外部依赖

def hash_password(password):
    """使用 PBKDF2-SHA256 哈希密码"""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"{salt}${h.hex()}"


def verify_password(password, password_hash):
    """验证密码"""
    try:
        salt, h_hex = password_hash.split('$', 1)
        h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return secrets.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


# ==================== 用户 CRUD ====================

def create_user(username, password, display_name=None):
    """创建用户，返回 user dict 或 None（用户名已存在）"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), display_name or username, _now())
        )
        conn.commit()
        return get_user_by_username(username)
    except sqlite3.IntegrityError:
        return None


def get_user_by_username(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


# ==================== 会话 CRUD ====================

SESSION_EXPIRE_HOURS = 72  # 3天


def create_session(user_id):
    """创建会话，返回 token"""
    conn = get_conn()
    token = secrets.token_hex(32)
    now = datetime.datetime.now()
    expires = now + datetime.timedelta(hours=SESSION_EXPIRE_HOURS)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now.strftime('%Y-%m-%d %H:%M:%S'), expires.strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    return token


def get_session_user(token):
    """根据 token 获取用户，过期返回 None"""
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ? AND s.expires_at > ?",
        (token, _now())
    ).fetchone()
    return dict(row) if row else None


def delete_session(token):
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


def cleanup_expired_sessions():
    """清理过期会话"""
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
    conn.commit()


# ==================== 团队 CRUD ====================

def create_team(name, creator_id):
    """创建团队，创建者自动成为 admin，返回 team dict"""
    conn = get_conn()
    invite_code = secrets.token_hex(4).upper()  # 8位大写
    now = _now()
    cursor = conn.execute(
        "INSERT INTO teams (name, invite_code, created_by, created_at) VALUES (?, ?, ?, ?)",
        (name, invite_code, creator_id, now)
    )
    team_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO team_members (team_id, user_id, role, joined_at) VALUES (?, ?, 'admin', ?)",
        (team_id, creator_id, now)
    )
    conn.commit()
    return get_team(team_id)


def get_team(team_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    return dict(row) if row else None


def join_team_by_code(invite_code, user_id):
    """通过邀请码加入团队，返回 team dict 或 None"""
    conn = get_conn()
    team = conn.execute("SELECT * FROM teams WHERE invite_code = ?", (invite_code.upper(),)).fetchone()
    if not team:
        return None
    team = dict(team)
    # 已经是成员则直接返回
    existing = conn.execute(
        "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
        (team['id'], user_id)
    ).fetchone()
    if existing:
        return team
    conn.execute(
        "INSERT INTO team_members (team_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
        (team['id'], user_id, _now())
    )
    conn.commit()
    return team


def get_user_teams(user_id):
    """获取用户所属的所有团队"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.*, tm.role FROM teams t
        JOIN team_members tm ON t.id = tm.team_id
        WHERE tm.user_id = ?
        ORDER BY tm.joined_at DESC
    """, (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_team_members(team_id):
    """获取团队成员列表"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.id, u.username, u.display_name, tm.role, tm.joined_at
        FROM team_members tm JOIN users u ON tm.user_id = u.id
        WHERE tm.team_id = ?
        ORDER BY tm.role DESC, tm.joined_at ASC
    """, (team_id,)).fetchall()
    return [dict(r) for r in rows]


def is_team_member(team_id, user_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id)
    ).fetchone()
    return row is not None


def leave_team(team_id, user_id):
    conn = get_conn()
    conn.execute(
        "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id)
    )
    # 如果团队没人了就删除团队
    remaining = conn.execute(
        "SELECT COUNT(*) as cnt FROM team_members WHERE team_id = ?",
        (team_id,)
    ).fetchone()['cnt']
    if remaining == 0:
        conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    conn.commit()


def remove_team_member(team_id, user_id):
    """管理员移除成员"""
    leave_team(team_id, user_id)


def get_team_member_role(team_id, user_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT role FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id)
    ).fetchone()
    return row['role'] if row else None


# ==================== 项目归属 ====================

def set_project_owner(project_id, owner_id):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO project_ownership (project_id, owner_id) VALUES (?, ?)",
        (project_id, owner_id)
    )
    conn.commit()


def get_project_owner(project_id):
    conn = get_conn()
    row = conn.execute("SELECT owner_id FROM project_ownership WHERE project_id = ?", (project_id,)).fetchone()
    return row['owner_id'] if row else None


def get_user_project_ids(user_id):
    """获取用户拥有的所有项目 ID"""
    conn = get_conn()
    rows = conn.execute("SELECT project_id FROM project_ownership WHERE owner_id = ?", (user_id,)).fetchall()
    return [r['project_id'] for r in rows]


# ==================== 项目分享 ====================

def share_project(project_id, team_id, shared_by):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO project_shares (project_id, team_id, shared_by, shared_at) VALUES (?, ?, ?, ?)",
            (project_id, team_id, shared_by, _now())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # 已分享


def unshare_project(project_id, team_id):
    conn = get_conn()
    conn.execute(
        "DELETE FROM project_shares WHERE project_id = ? AND team_id = ?",
        (project_id, team_id)
    )
    conn.commit()


def get_team_project_ids(team_id):
    """获取团队中分享的所有项目 ID"""
    conn = get_conn()
    rows = conn.execute("SELECT project_id FROM project_shares WHERE team_id = ?", (team_id,)).fetchall()
    return [r['project_id'] for r in rows]


def get_project_shared_teams(project_id):
    """获取项目分享到的所有团队"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.id, t.name FROM project_shares ps
        JOIN teams t ON ps.team_id = t.id
        WHERE ps.project_id = ?
    """, (project_id,)).fetchall()
    return [dict(r) for r in rows]


def can_user_access_project(project_id, user_id):
    """检查用户是否有权限访问项目（拥有者 OR 同团队）"""
    # 拥有者
    if get_project_owner(project_id) == user_id:
        return True
    # 通过团队分享
    conn = get_conn()
    row = conn.execute("""
        SELECT 1 FROM project_shares ps
        JOIN team_members tm ON ps.team_id = tm.team_id
        WHERE ps.project_id = ? AND tm.user_id = ?
        LIMIT 1
    """, (project_id, user_id)).fetchone()
    return row is not None


def delete_project_ownership(project_id):
    """删除项目归属和所有分享记录"""
    conn = get_conn()
    conn.execute("DELETE FROM project_ownership WHERE project_id = ?", (project_id,))
    conn.execute("DELETE FROM project_shares WHERE project_id = ?", (project_id,))
    conn.commit()
