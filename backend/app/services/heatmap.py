"""HeatmapService – HeatmapAggregator: tính chỉ số nút, phân màu BR-06, truy vết gốc, đẩy WebSocket (mục 6.5).
Chủ: Long (C2-11…C2-13).
"""


class HeatmapService:
    def recompute(self, class_id, node_id):
        raise NotImplementedError("C2-11")

    def classify(self, stat, settings):
        raise NotImplementedError("C2-11")

    def snapshot(self, class_id):
        raise NotImplementedError("C2-13")

    def node_detail(self, class_id, node_id):
        raise NotImplementedError("C2-13")
