"""
services/knowledge_base.py
Knowledge Base Service - SQLite + FTS5 for RAG.
Hỗ trợ: .txt, .md, .py, URL web, raw text.
Tìm kiếm: FTS5 full-text search + AI Core augmentation.
Web: DuckDuckGo search + fetch & learn.
"""

from __future__ import annotations

import aiosqlite
import asyncio
import hashlib
import logging
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urljoin

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("KnowledgeBase")

# ============================================================
# CONFIG
# ============================================================
KB_DIR = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))) / "data" / "knowledge_base"
KB_DIR.mkdir(parents=True, exist_ok=True)
KB_DB = KB_DIR / "knowledge.db"

MAX_CHUNK_SIZE = 2000
MAX_FILE_SIZE = 2_000_000
ALLOWED_EXTENSIONS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".log"}

# ============================================================
# DATABASE SCHEMA
# ============================================================
SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS kb_chunks (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT UNIQUE NOT NULL,
    content_hash TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_path TEXT DEFAULT '',
    chunk_index INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    content TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_sources (
    source_name TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_path TEXT DEFAULT '',
    total_chunks INTEGER DEFAULT 0,
    total_chars INTEGER DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_update TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
    content,
    content_rowid='rowid',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS kb_chunks_ai AFTER INSERT ON kb_chunks BEGIN
    INSERT INTO kb_fts (rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS kb_chunks_ad AFTER DELETE ON kb_chunks BEGIN
    DELETE FROM kb_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS kb_chunks_au AFTER UPDATE ON kb_chunks BEGIN
    UPDATE kb_fts SET content = new.content WHERE rowid = old.rowid;
END;

CREATE INDEX IF NOT EXISTS idx_kb_chunks_hash ON kb_chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_source ON kb_chunks(source_name);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_chunk_id ON kb_chunks(chunk_id);
"""

# ============================================================
# UTILS
# ============================================================

def _chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    if len(text) <= max_size:
        return [text]
    
    chunks = []
    paragraphs = text.split("\n\n")
    current = ""
    
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_size:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                chunks.append(current)
            if len(para) > max_size:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= max_size:
                        current += (" " if current else "") + sent
                    else:
                        if current:
                            chunks.append(current)
                        current = sent
            else:
                current = para
    
    if current:
        chunks.append(current)
    
    return chunks

def _extract_text_from_url(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            html = res.read().decode("utf-8", errors="ignore")
        
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    except Exception as e:
        raise ValueError(f"Không thể fetch URL: {e}")

def _compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]

# ============================================================
# KNOWLEDGE BASE CLASS
# ============================================================

class KnowledgeBase:
    def __init__(self):
        self.db_path = KB_DB
        self._initialized = False

    async def _init_db(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        self._initialized = True

    # ========================================================
    # INGEST METHODS
    # ========================================================

    async def ingest_file(self, file_path: str, source_name: Optional[str] = None) -> dict[str, Any]:
        await self._init_db()
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File không tồn tại: {file_path}"}
        
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            return {"success": False, "error": f"Định dạng không hỗ trợ: {path.suffix}"}
        
        if path.stat().st_size > MAX_FILE_SIZE:
            return {"success": False, "error": f"File quá lớn (>2MB)"}

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return {"success": False, "error": f"Đọc file lỗi: {e}"}

        return await self.ingest_text(content, source_name or path.name, source_type="file", source_path=str(path))

    async def ingest_url(self, url: str, source_name: Optional[str] = None) -> dict[str, Any]:
        await self._init_db()
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {"success": False, "error": "URL không hợp lệ"}

        try:
            content = _extract_text_from_url(url)
        except Exception as e:
            return {"success": False, "error": str(e)}

        if not content.strip():
            return {"success": False, "error": "URL không có nội dung text"}

        name = source_name or f"URL: {parsed.netloc}"
        return await self.ingest_text(content, name, source_type="url", source_path=url)

    async def ingest_text(self, text: str, source_name: str, source_type: str = "text", source_path: str = "") -> dict[str, Any]:
        await self._init_db()
        if not text or not text.strip():
            return {"success": False, "error": "Nội dung rỗng"}

        text = text.strip()
        content_hash = _compute_hash(text)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT chunk_id FROM kb_chunks WHERE content_hash = ? LIMIT 1", (content_hash,))
            if await cursor.fetchone():
                return {"success": False, "error": "Nội dung đã tồn tại (duplicate)"}

            chunks = _chunk_text(text)
            now = datetime.now().isoformat()
            ingested = 0
            
            for i, chunk in enumerate(chunks):
                chunk_id = f"{content_hash}_{i}"
                await db.execute("""
                    INSERT INTO kb_chunks (chunk_id, content_hash, source_name, source_type, source_path, 
                                          chunk_index, total_chunks, content, char_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (chunk_id, content_hash, source_name, source_type, source_path,
                      i, len(chunks), chunk, len(chunk), now))
                ingested += 1
            
            await db.execute("""
                INSERT INTO kb_sources (source_name, source_type, source_path, total_chunks, total_chars, first_seen, last_update)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    total_chunks = total_chunks + excluded.total_chunks,
                    total_chars = total_chars + excluded.total_chars,
                    last_update = excluded.last_update
            """, (source_name, source_type, source_path, len(chunks), len(text), now, now))
            
            await db.commit()

        logger.info(f"KB ingested: {source_name} ({source_type}) - {ingested} chunks")
        return {
            "success": True,
            "source_name": source_name,
            "source_type": source_type,
            "chunks": ingested,
            "total_chars": len(text),
        }

    # ========================================================
    # SEARCH & RETRIEVAL (RAG)
    # ========================================================

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        await self._init_db()
        
        query_words = [w for w in re.findall(r'\w+', query.lower()) if len(w) >= 2]
        if not query_words:
            return []
        
        fts_query = " OR ".join(f'"{w}"*' for w in query_words)
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT c.*, bm25(kb_fts) as rank
                FROM kb_chunks c
                JOIN kb_fts ON kb_fts.rowid = c.rowid
                WHERE kb_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ?
            """, (fts_query, top_k))
            
            rows = await cursor.fetchall()
            
        results = []
        for row in rows:
            item = dict(row)
            item["relevance"] = 1.0 / (1.0 + item.pop("rank", 1.0))
            results.append(item)
        
        return results

    async def get_context_for_query(
        self, query: str, max_chars: int = 4000, min_relevance: float = 0.25
    ) -> str:
        """Lấy context RAG, LOẠI kết quả relevance thấp (tránh KB rác làm nhiễu câu trả lời)."""
        results = await self.search(query, top_k=8)
        results = [r for r in results if r.get("relevance", 0.0) >= min_relevance]
        if not results:
            return ""

        context_parts = []
        total = 0
        for r in results:
            snippet = f"[{r['source_name']} ({r['source_type']})] {r['content'][:1000]}"
            if total + len(snippet) > max_chars:
                break
            context_parts.append(snippet)
            total += len(snippet)

        return "\n\n---\n\n".join(context_parts)

    # ========================================================
    # MANAGEMENT
    # ========================================================

    async def list_sources(self) -> list[dict[str, Any]]:
        await self._init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM kb_sources ORDER BY last_update DESC")
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_source(self, source_name: str) -> dict[str, Any]:
        await self._init_db()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM kb_chunks WHERE source_name = ?", (source_name,))
            deleted = cursor.rowcount
            await db.execute("DELETE FROM kb_sources WHERE source_name = ?", (source_name,))
            await db.commit()
        return {"success": deleted > 0, "deleted_chunks": deleted}

    async def clear_all(self) -> dict[str, Any]:
        await self._init_db()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM kb_chunks")
            count = cursor.rowcount
            await db.execute("DELETE FROM kb_sources")
            await db.commit()
        return {"success": True, "deleted_chunks": count}

    async def stats(self) -> dict[str, Any]:
        await self._init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COUNT(*) as chunks, SUM(char_count) as chars FROM kb_chunks")
            row = await cursor.fetchone()
            cursor = await db.execute("SELECT COUNT(*) as sources FROM kb_sources")
            src = await cursor.fetchone()
        
        size_mb = round(self.db_path.stat().st_size / (1024*1024), 2) if self.db_path.exists() else 0
        return {
            "total_chunks": row["chunks"] or 0,
            "total_sources": src["sources"] or 0,
            "total_chars": row["chars"] or 0,
            "storage_mb": size_mb,
        }

    # ========================================================
    # WEB SEARCH INTEGRATION
    # ========================================================

    async def web_search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        return await search_web(query, max_results)

    async def search_and_learn(self, query: str, max_sources: int = 3) -> dict[str, Any]:
        return await search_and_ingest(query, max_sources)

    async def fetch_and_learn(self, url: str, source_name: Optional[str] = None) -> dict[str, Any]:
        content = await fetch_url_content(url)
        if not content or len(content) < 200:
            return {"success": False, "error": "Không fetch được nội dung hoặc quá ít"}
        
        name = source_name or url
        return await self.ingest_text(content[:50000], name, source_type="web_fetch", source_path=url)


# Singleton instance (created after class definition)
kb = KnowledgeBase()


# ============================================================
# STANDALONE WEB FUNCTIONS (use singleton kb)
# ============================================================

async def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Tìm kiếm web qua DuckDuckGo (thử nhiều endpoint + pattern, no API key needed)."""
    UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    encoded = urllib.parse.quote_plus(query)
    endpoints = [
        f"https://html.duckduckgo.com/html/?q={encoded}",
        f"https://lite.duckduckgo.com/lite/?q={encoded}",
    ]

    def _norm_url(u: str) -> str:
        u = (u or "").strip()
        if not u:
            return ""
        # DuckDuckGo redirect links: //duckduckgo.com/l/?uddg=<real url>
        m = re.search(r"[?&]uddg=([^&]+)", u)
        if m:
            try:
                return urllib.parse.unquote(m.group(1))
            except Exception:
                pass
        if u.startswith("//"):
            return "https:" + u
        if not u.startswith("http"):
            return f"https://{u}"
        return u

    def _clean(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text or "")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    patterns = [
        # html.duckduckgo.com classic
        r'class="result__snippet">(.*?)</a>.*?class="result__url">(.*?)</span>',
        r'class="result__title"><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        # lite.duckduckgo.com
        r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</td>.*?(?:<td[^>]*>(.*?)</td>)?',
    ]

    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers=UA)

            def _fetch(req=req):
                with urllib.request.urlopen(req, timeout=10) as res:
                    return res.read().decode("utf-8", errors="ignore")

            html = await asyncio.to_thread(_fetch)
            if not html:
                continue

            results: list[dict[str, str]] = []
            for pattern in patterns:
                for match in re.findall(pattern, html, re.DOTALL):
                    if isinstance(match, tuple):
                        if len(match) == 2 and "snippet" in pattern:
                            snippet, url_text = match
                            snippet, url_text = _clean(snippet), _norm_url(_clean(url_text))
                            if snippet and url_text:
                                results.append({"title": snippet[:100], "snippet": snippet, "url": url_text})
                        elif len(match) == 2:
                            link, title = match
                            link, title = _norm_url(link), _clean(title)
                            if link and title and "duckduckgo.com" not in link:
                                results.append({"title": title[:100], "snippet": "", "url": link})
                        elif len(match) == 3:
                            link, title, snippet = match
                            link, title, snippet = _norm_url(link), _clean(title), _clean(snippet)
                            if link and "duckduckgo.com" not in link and (title or snippet):
                                results.append({
                                    "title": (title or snippet)[:100],
                                    "snippet": snippet or title,
                                    "url": link,
                                })
                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break

            if results:
                return results[:max_results]
        except Exception as e:
            logger.warning(f"Web search error ({url[:40]}...): {e}")
            continue

    return []

async def fetch_url_content(url: str) -> Optional[str]:
    try:
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        
        def _fetch():
            with urllib.request.urlopen(req, timeout=15) as res:
                content_type = res.headers.get("Content-Type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return None
                return res.read().decode("utf-8", errors="ignore")
        
        html = await asyncio.to_thread(_fetch)
        if not html:
            return None
        
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<aside[^>]*>.*?</aside>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()[:50000]
    except Exception as e:
        logger.warning(f"Fetch URL error: {e}")
        return None

async def search_and_ingest(query: str, max_sources: int = 3, max_chars_per_source: int = 15000) -> dict[str, Any]:
    """Tìm kiếm web, fetch nội dung, và ingest vào KB."""
    results = await search_web(query, max_results=max_sources)
    if not results:
        return {"success": False, "error": "Không tìm thấy kết quả"}
    
    ingested = 0
    errors = []
    
    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        
        content = await fetch_url_content(url)
        if not content or len(content) < 200:
            errors.append(f"{url}: nội dung quá ít")
            continue
        
        content = content[:max_chars_per_source]
        source_name = r.get("title", url) or url
        result = await kb.ingest_text(content, source_name, source_type="web_search", source_path=url)
        if result.get("success"):
            ingested += 1
        else:
            errors.append(f"{url}: {result.get('error')}")
    
    return {
        "success": ingested > 0,
        "ingested": ingested,
        "errors": errors,
        "query": query,
    }