"""
services/embedding_service.py
Dịch vụ Semantic Vector Embedding & Tìm kiếm ngữ nghĩa siêu tốc cho tài liệu học tập.
Sử dụng mô hình đa ngôn ngữ ONNX (Vietnamese + English) qua fastembed và tăng tốc SIMD C++ qua bridge.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
from typing import TYPE_CHECKING, List, Optional, Tuple

import numpy as np

if TYPE_CHECKING:
    from database.database import Database

try:
    from fastembed import TextEmbedding
    HAS_FASTEMBED = True
except ImportError:
    TextEmbedding = None  # type: ignore
    HAS_FASTEMBED = False

from cpp_core.bridge import fast_batch_cosine

log = logging.getLogger("EmbeddingService")

DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


class DocumentEmbeddingService:
    """
    Quản lý sinh vector embedding và tra cứu ngữ nghĩa (Semantic Search) cho kho tài liệu.
    Hỗ trợ tìm kiếm theo ý nghĩa thực sự (ví dụ: 'bài toán đạo hàm' tìm ra 'vận tốc chuyển động').
    """

    _instance: Optional[DocumentEmbeddingService] = None

    def __init__(self, db: Optional[Database] = None, model_name: str = DEFAULT_MODEL_NAME):
        self.db = db
        self.model_name = model_name
        self._model: Optional[TextEmbedding] = None
        self._model_loading = False
        self._model_lock = asyncio.Lock()

        # In-memory vector index (RAM cache cho tra cứu sub-millisecond)
        self._doc_ids: List[int] = []
        self._vector_matrix: Optional[np.ndarray] = None  # shape (N, 384), float32
        self._is_cache_ready = False
        self._sync_task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls, db: Optional[Database] = None) -> DocumentEmbeddingService:
        if cls._instance is None:
            cls._instance = cls(db=db)
        elif db is not None and cls._instance.db is None:
            cls._instance.db = db
        return cls._instance

    def _resolve_providers(self) -> list:
        """Chọn execution providers theo cấu hình + phần cứng thực tế.

        - cpu: chỉ CPU.
        - cuda: chỉ CUDA (lỗi → caller fallback CPU).
        - auto: có CUDA provider thì ưu tiên GPU (kèm trần VRAM), sau đó CPU
          đỡ. Không có GPU → CPU thuần.
        """
        try:
            from config.settings import settings
            device = str(getattr(settings, "EMBEDDING_DEVICE", "auto") or "auto").lower()
            vram_gb = float(getattr(settings, "EMBEDDING_GPU_MEM_GB", 1.0) or 1.0)
        except Exception:
            device, vram_gb = "auto", 1.0
        if device not in ("auto", "cpu", "cuda"):
            log.warning("EMBEDDING_DEVICE=%s không hợp lệ, dùng 'auto'.", device)
            device = "auto"

        cuda_available = False
        try:
            import onnxruntime as _ort
            cuda_available = "CUDAExecutionProvider" in _ort.get_available_providers()
        except Exception:
            cuda_available = False

        if device == "cpu" or not cuda_available:
            return ["CPUExecutionProvider"]
        vram_bytes = max(int(vram_gb * (1024 ** 3)), 256 * 1024 * 1024)
        cuda_opts = {
            "arena_extend_strategy": "kSameAsRequested",
            "gpu_mem_limit": vram_bytes,
        }
        if device == "cuda":
            return [("CUDAExecutionProvider", cuda_opts)]
        return [("CUDAExecutionProvider", cuda_opts), "CPUExecutionProvider"]

    def _ensure_model_sync(self) -> Optional[TextEmbedding]:
        """Tải model TextEmbedding (đồng bộ trong thread riêng)."""
        if self._model is not None:
            return self._model
        if not HAS_FASTEMBED:
            log.warning("Thư viện fastembed chưa được cài đặt. Semantic Search bị vô hiệu hóa.")
            return None
        providers = self._resolve_providers()
        try:
            t0 = time.perf_counter()
            self._model = TextEmbedding(self.model_name, providers=providers)
            prov_names = [p if isinstance(p, str) else p[0] for p in providers]
            log.info(
                "Đã nạp thành công mô hình Embedding [%s] trong %.2fs (providers=%s)",
                self.model_name,
                time.perf_counter() - t0,
                prov_names,
            )
            return self._model
        except Exception as e:
            # GPU lỗi/thiếu VRAM → rớt về CPU thuần 1 lần cuối
            if any("CUDA" in (p if isinstance(p, str) else p[0]) for p in providers):
                log.warning("Nạp model bằng GPU thất bại (%s). Thử lại bằng CPU...", e)
                try:
                    t0 = time.perf_counter()
                    self._model = TextEmbedding(self.model_name, providers=["CPUExecutionProvider"])
                    log.info(
                        "Đã nạp mô hình Embedding [%s] bằng CPU trong %.2fs",
                        self.model_name,
                        time.perf_counter() - t0,
                    )
                    return self._model
                except Exception as e2:
                    log.error("Không thể tải mô hình FastEmbed [%s]: %s", self.model_name, e2)
                    return None
            log.error("Không thể tải mô hình FastEmbed [%s]: %s", self.model_name, e)
            return None

    async def get_model(self) -> Optional[TextEmbedding]:
        """Lấy instance model, khởi tạo bất đồng bộ nếu chưa nạp."""
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is not None:
                return self._model
            return await asyncio.to_thread(self._ensure_model_sync)

    def _embed_texts_sync(self, texts: List[str]) -> List[np.ndarray]:
        """Sinh embedding cho danh sách văn bản (chạy trong worker thread)."""
        model = self._ensure_model_sync()
        if model is None or not texts:
            return []
        try:
            embeddings = list(model.embed(texts))
            return [np.ascontiguousarray(e, dtype=np.float32) for e in embeddings]
        except Exception as e:
            log.error("Lỗi khi sinh vector embedding: %s", e)
            return []

    async def embed_text(self, text: str) -> Optional[np.ndarray]:
        """Sinh vector embedding cho 1 đoạn văn bản."""
        if not text or not text.strip():
            return None
        res = await asyncio.to_thread(self._embed_texts_sync, [text])
        return res[0] if res else None

    async def load_cache_from_db(self) -> None:
        """Đọc toàn bộ vector đã lưu trong SQLite vào RAM để tìm kiếm tức thì."""
        if not self.db:
            return
        try:
            rows = await self.db.fetchall(
                "SELECT doc_id, embedding, dim FROM document_embeddings WHERE model_name = ?",
                self.model_name,
            )
            if not rows:
                self._doc_ids = []
                self._vector_matrix = None
                self._is_cache_ready = True
                return

            doc_ids = []
            vectors = []
            for r in rows:
                doc_id, blob, dim = r[0], r[1], r[2]
                if blob and dim == EMBEDDING_DIM:
                    vec = np.frombuffer(blob, dtype=np.float32)
                    if vec.shape[0] == EMBEDDING_DIM:
                        doc_ids.append(doc_id)
                        vectors.append(vec)

            if vectors:
                self._doc_ids = doc_ids
                self._vector_matrix = np.ascontiguousarray(np.vstack(vectors), dtype=np.float32)
                log.info(
                    "Đã nạp %d vector embeddings vào RAM (Dung lượng: %.2f KB)",
                    len(doc_ids),
                    (self._vector_matrix.nbytes / 1024.0),
                )
            else:
                self._doc_ids = []
                self._vector_matrix = None

            self._is_cache_ready = True
        except Exception as e:
            log.warning("Lỗi nạp vector embeddings từ CSDL: %s", e)
            self._is_cache_ready = False

    async def embed_and_save_document(
        self,
        doc_id: int,
        subject: str,
        title: str,
        file_name: str,
        raw_text: Optional[str] = None,
    ) -> bool:
        """
        Bóc tách ngữ cảnh, sinh vector embedding và lưu vào CSDL cho 1 tài liệu.
        Đồng thời cập nhật RAM cache ngay lập tức.
        """
        if not self.db:
            return False

        # Ghép chuỗi ngữ cảnh toàn diện: Môn học + Tiêu đề + Tên file + Nội dung đầu
        parts = [subject or "", title or "", file_name or ""]
        if raw_text:
            parts.append(raw_text[:2000])
        combined_text = " ".join(p for p in parts if p).strip()

        if not combined_text:
            return False

        vec = await self.embed_text(combined_text)
        if vec is None or vec.shape[0] != EMBEDDING_DIM:
            return False

        blob = vec.tobytes()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        try:
            await self.db.execute(
                """
                INSERT INTO document_embeddings (doc_id, model_name, embedding, dim, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    model_name = excluded.model_name,
                    embedding = excluded.embedding,
                    dim = excluded.dim,
                    updated_at = excluded.updated_at
                """,
                doc_id,
                self.model_name,
                blob,
                EMBEDDING_DIM,
                now_iso,
            )

            # Cập nhật RAM cache
            if self._vector_matrix is not None and doc_id in self._doc_ids:
                idx = self._doc_ids.index(doc_id)
                self._vector_matrix[idx] = vec
            else:
                self._doc_ids.append(doc_id)
                if self._vector_matrix is None:
                    self._vector_matrix = np.ascontiguousarray(vec.reshape(1, -1), dtype=np.float32)
                else:
                    self._vector_matrix = np.ascontiguousarray(
                        np.vstack([self._vector_matrix, vec]), dtype=np.float32
                    )

            log.debug("Đã cập nhật vector embedding cho doc_id: %d", doc_id)
            return True
        except Exception as e:
            log.error("Lỗi lưu vector embedding cho doc_id %d: %s", doc_id, e)
            return False

    async def sync_missing_documents(self) -> int:
        """
        Quét các tài liệu trong documents_archive chưa có vector embedding
        và tự động sinh embedding bổ sung.
        """
        if not self.db:
            return 0

        # Lấy danh sách doc_id chưa có embedding
        try:
            missing_rows = await self.db.fetchall(
                """
                SELECT d.id, d.subject, d.title, d.file_name, d.raw_text
                FROM documents_archive d
                LEFT JOIN document_embeddings e ON d.id = e.doc_id AND e.model_name = ?
                WHERE e.doc_id IS NULL
                """,
                self.model_name,
            )
            if not missing_rows:
                # Nếu không có tài liệu nào thiếu, nạp cache nếu chưa sẵn sàng
                if not self._is_cache_ready:
                    await self.load_cache_from_db()
                return 0

            log.info("Tìm thấy %d tài liệu chưa có vector embedding. Bắt đầu sinh...", len(missing_rows))

            doc_ids = []
            texts = []
            for r in missing_rows:
                d_id, subj, title, fname, rtext = r[0], r[1], r[2], r[3], r[4]
                parts = [subj or "", title or "", fname or ""]
                if rtext:
                    parts.append(rtext[:2000])
                texts.append(" ".join(p for p in parts if p).strip())
                doc_ids.append(d_id)

            # Sinh embedding theo batch nhỏ (16 docs/batch) để tránh nghẽn CPU
            batch_size = 16
            saved_count = 0
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i : i + batch_size]
                batch_ids = doc_ids[i : i + batch_size]

                batch_vecs = await asyncio.to_thread(self._embed_texts_sync, batch_texts)
                for d_id, vec in zip(batch_ids, batch_vecs):
                    if vec is not None and vec.shape[0] == EMBEDDING_DIM:
                        await self.db.execute(
                            """
                            INSERT INTO document_embeddings (doc_id, model_name, embedding, dim, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(doc_id) DO UPDATE SET
                                model_name = excluded.model_name,
                                embedding = excluded.embedding,
                                dim = excluded.dim,
                                updated_at = excluded.updated_at
                            """,
                            d_id,
                            self.model_name,
                            vec.tobytes(),
                            EMBEDDING_DIM,
                            now_iso,
                        )
                        saved_count += 1
                await asyncio.sleep(0.01)

            # Nạp lại toàn bộ cache sau khi hoàn tất
            await self.load_cache_from_db()
            log.info("Đã đồng bộ thành công %d vector embeddings mới!", saved_count)
            return saved_count
        except Exception as e:
            log.error("Lỗi trong quá trình sync missing documents: %s", e)
            return 0

    async def search_semantic(
        self, query: str, limit: int = 30, min_score: float = 0.20
    ) -> List[Tuple[int, float]]:
        """
        Tra cứu ngữ nghĩa bằng Cosine Similarity tăng tốc C++ SIMD.
        Trả về danh sách (doc_id, score) sắp xếp theo độ tương đồng giảm dần.
        """
        if not query or not query.strip():
            return []

        # Đảm bảo cache RAM đã nạp
        if not self._is_cache_ready:
            await self.load_cache_from_db()

        if self._vector_matrix is None or len(self._doc_ids) == 0:
            return []

        # Sinh vector embedding cho câu truy vấn
        q_vec = await self.embed_text(query)
        if q_vec is None or q_vec.shape[0] != EMBEDDING_DIM:
            return []

        # Tính similarity siêu tốc qua C++ / NumPy
        scores = fast_batch_cosine(q_vec, self._vector_matrix)
        if not scores or len(scores) != len(self._doc_ids):
            return []

        # Lọc và sắp xếp theo score giảm dần
        results = []
        for doc_id, score in zip(self._doc_ids, scores):
            if score >= min_score:
                results.append((doc_id, float(score)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def start_background_sync(self) -> None:
        """Khởi động tác vụ nền nạp model và đồng bộ embedding không làm đơ bot."""
        if self._sync_task is None or self._sync_task.done():
            async def _worker():
                try:
                    await self.get_model()
                    await self.sync_missing_documents()
                except Exception as e:
                    log.warning("Embedding background sync gặp lỗi: %s", e)

            self._sync_task = asyncio.create_task(_worker())
