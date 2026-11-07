"""RetrievalService – RAG trên document_chunks (pgvector, HNSW cosine) – trích dẫn trang (mục 2.2.3). Chủ: Đăng
(C1-11).
"""


class RetrievalService:
    def retrieve(self, node_id, query, k=5):
        raise NotImplementedError("C1-11")
