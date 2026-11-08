"""Cây kỹ năng của các lớp mẫu, khai báo bằng văn bản: `mã | tên | chương | bloom | tiên quyết`.

Bloom: R nhớ · U hiểu · A áp dụng · N phân tích · E đánh giá · C sáng tạo.
Tiên quyết: mã nút cách nhau dấu phẩy, `-` là nút gốc.
Cây CTDL&GT mở rộng từ 11 nút của `seed/tree_ctdl_gt.json` (giữ nguyên khóa, tiêu đề, rubric đã duyệt).
"""

import json
import re
import unicodedata
from pathlib import Path

from app.algorithms.dag import build_graph, find_cycle, layers
from app.models.enums import BloomLevel, EdgeSource, TreeStatus
from app.models.schemas.tree import Edge, Node, TreeVersion


def _fixture_path() -> Path:
    default_p = Path(__file__).resolve().parents[2] / "seed" / "tree_ctdl_gt.json"
    if default_p.exists():
        return default_p
    container_p = Path("/seed/tree_ctdl_gt.json")
    if container_p.exists():
        return container_p
    return default_p


FIXTURE = _fixture_path()
BLOOM = {
    "R": BloomLevel.REMEMBER,
    "U": BloomLevel.UNDERSTAND,
    "A": BloomLevel.APPLY,
    "N": BloomLevel.ANALYZE,
    "E": BloomLevel.EVALUATE,
    "C": BloomLevel.CREATE,
}


def slug(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40]


def fixture_tree() -> TreeVersion:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return TreeVersion.model_validate({k: v for k, v in raw.items() if not k.startswith("_")})


def build(spec: str, *, status: TreeStatus = TreeStatus.PUBLISHED, base: TreeVersion | None = None) -> TreeVersion:
    nodes = [n.model_copy(deep=True) for n in base.nodes] if base else []
    edges = [e.model_copy(deep=True) for e in base.edges] if base else []
    key_of = {n.code: n.key for n in nodes}
    for raw in spec.strip().splitlines():
        code, title, chapter, bloom, pre = (p.strip() for p in raw.split("|"))
        key = f"{code.lower()}_{slug(title)}"
        key_of[code] = key
        nodes.append(Node(key=key, code=code, title=title, chapter_ref=chapter, bloom_level=BLOOM[bloom]))
        for p in () if pre == "-" else (x.strip() for x in pre.split(",")):
            edges.append(Edge(from_key=key_of[p], to_key=key, source=EdgeSource.LECTURER))
    tree = TreeVersion(version_no=1, status=status, change_note="Dữ liệu mẫu", nodes=nodes, edges=edges)
    g = build_graph(tree)
    if cycle := find_cycle(g):
        raise ValueError(f"cây có chu trình: {' → '.join(cycle)}")
    layer_of, used = layers(g), {}
    for n in tree.nodes:
        layer = layer_of[n.key]
        n.position_x, n.position_y = used.get(layer, 0) * 220.0, layer * 150.0
        used[layer] = used.get(layer, 0) + 1
        if n.rubric is not None:
            n.rubric.approved = status == TreeStatus.PUBLISHED
    return tree


CTDL = """
N12 | Chuỗi ký tự | Chương 2 | U | N2
N13 | Mảng hai chiều | Chương 2 | A | N2
N14 | Con trỏ và mảng | Chương 3 | A | N5, N2
N15 | Tìm kiếm tuyến tính và nhị phân | Chương 6 | A | N2
N16 | Sắp xếp cơ bản | Chương 6 | A | N2
N17 | Sắp xếp nhanh và sắp xếp trộn | Chương 6 | N | N16, N4
N18 | Danh sách liên kết đôi và vòng | Chương 4 | A | N7
N19 | Biểu thức hậu tố | Chương 4 | A | N8
N20 | Duyệt cây | Chương 5 | A | N9
N21 | Heap và hàng đợi ưu tiên | Chương 5 | A | N9, N16
N22 | Bảng băm | Chương 6 | A | N2, N15
N23 | Biểu diễn đồ thị | Chương 7 | U | N7, N2
N24 | Duyệt đồ thị BFS và DFS | Chương 7 | A | N23, N8
N25 | Đường đi ngắn nhất Dijkstra | Chương 7 | N | N24, N21
N26 | Cây khung nhỏ nhất | Chương 7 | N | N24, N21
"""

NMLT = """
P1 | Biến và kiểu dữ liệu | Chương 1 | U | -
P2 | Toán tử và biểu thức | Chương 1 | U | P1
P3 | Rẽ nhánh if/else | Chương 2 | A | P2
P4 | Vòng lặp | Chương 2 | A | P2
P5 | Vòng lặp lồng nhau | Chương 2 | A | P4
P6 | Hàm | Chương 3 | A | P3, P4
P7 | Phạm vi biến | Chương 3 | U | P6
P8 | Đệ quy cơ bản | Chương 3 | A | P6
P9 | Danh sách và mảng | Chương 4 | A | P4
P10 | Chuỗi | Chương 4 | A | P9
P11 | Đọc ghi tệp | Chương 5 | A | P6, P10
P12 | Gỡ lỗi và kiểm thử | Chương 5 | E | P6
"""

MMT = """
M1 | Tổng quan mạng máy tính | Chương 1 | R | -
M2 | Mô hình OSI | Chương 1 | U | M1
M3 | Mô hình TCP/IP | Chương 1 | U | M1
M4 | Đóng gói dữ liệu | Chương 1 | U | M2, M3
M5 | Môi trường truyền và cáp | Chương 2 | R | M1
M6 | Ethernet và địa chỉ MAC | Chương 2 | U | M5, M2
M7 | Switch và VLAN | Chương 2 | A | M6
M8 | Địa chỉ IPv4 | Chương 3 | U | M3
M9 | Chia mạng con | Chương 3 | A | M8
M10 | IPv6 | Chương 3 | U | M8
M11 | ARP | Chương 3 | U | M6, M8
M12 | Định tuyến tĩnh | Chương 3 | A | M9, M11
M13 | Định tuyến động RIP và OSPF | Chương 3 | A | M12
M14 | NAT | Chương 3 | U | M9
M15 | ICMP và ping | Chương 3 | A | M11
M16 | UDP | Chương 4 | U | M3
M17 | TCP và bắt tay ba bước | Chương 4 | U | M3
M18 | Điều khiển luồng TCP | Chương 4 | A | M17
M19 | Điều khiển tắc nghẽn | Chương 4 | A | M18
M20 | Cổng và socket | Chương 4 | A | M16, M17
M21 | DNS | Chương 5 | U | M20, M8
M22 | DHCP | Chương 5 | U | M16, M11
M23 | HTTP | Chương 5 | U | M17, M21
M24 | HTTPS và TLS | Chương 5 | A | M23
M25 | Thư điện tử SMTP và IMAP | Chương 5 | U | M21, M17
M26 | FTP và SSH | Chương 5 | U | M17
M27 | Mật mã và chữ ký số | Chương 6 | U | M24
M28 | Tường lửa | Chương 6 | A | M14, M17
M29 | VPN | Chương 6 | A | M24, M28
M30 | Tấn công mạng phổ biến | Chương 6 | N | M28
M31 | Wi-Fi và bảo mật không dây | Chương 6 | A | M7, M24
M32 | Giám sát và khắc phục sự cố | Chương 6 | E | M15, M13
"""

CSDL = """
D1 | Mô hình dữ liệu quan hệ | Chương 1 | U | -
D2 | Khóa chính và khóa ngoại | Chương 1 | U | D1
D3 | Truy vấn SELECT cơ bản | Chương 2 | A | D1
D4 | Lọc và sắp xếp WHERE ORDER BY | Chương 2 | A | D3
D5 | Hàm tổng hợp và GROUP BY | Chương 2 | A | D4
D6 | Phép nối JOIN | Chương 2 | A | D2, D4
D7 | Truy vấn con | Chương 2 | A | D6
D8 | INSERT UPDATE DELETE | Chương 3 | A | D3
D9 | Ràng buộc toàn vẹn | Chương 3 | U | D2, D8
D10 | Chuẩn hóa 1NF đến 3NF | Chương 4 | A | D2
D11 | Chuẩn BCNF | Chương 4 | A | D10
D12 | Thiết kế mô hình ER | Chương 4 | C | D1
D13 | Chỉ mục | Chương 5 | U | D3
D14 | Giao dịch và ACID | Chương 5 | U | D8
D15 | Khóa và truy cập đồng thời | Chương 5 | A | D14
D16 | View và thủ tục lưu trữ | Chương 5 | A | D7, D8
D17 | Trigger | Chương 5 | A | D16, D9
D18 | Sao lưu và phục hồi | Chương 5 | U | D14
"""

HDH = """
O1 | Tổng quan hệ điều hành | Chương 1 | R | -
O2 | Tiến trình và luồng | Chương 1 | U | O1
O3 | Lập lịch CPU | Chương 2 | A | O2
O4 | Đồng bộ hóa tiến trình | Chương 2 | A | O2
O5 | Mutex và Semaphore | Chương 2 | A | O4
O6 | Bế tắc Deadlock | Chương 2 | N | O5
O7 | Quản lý bộ nhớ chính | Chương 3 | U | O1
O8 | Phân trang và phân đoạn | Chương 3 | A | O7
O9 | Bộ nhớ ảo và thay thế trang | Chương 3 | A | O8
O10 | Cấu trúc hệ thống tệp | Chương 4 | U | O1
O11 | Cài đặt hệ thống tệp | Chương 4 | A | O10
O12 | Quản lý vào ra IO | Chương 5 | U | O1
O13 | Bảo mật và bảo vệ hệ thống | Chương 5 | U | O10
O14 | Hệ thống phân tán và ảo hóa | Chương 6 | U | O2, O10
"""

LTW = """
W1 | HTML cơ bản | Chương 1 | U | -
W2 | CSS cơ bản | Chương 1 | U | W1
W3 | Bố cục Flexbox và Grid | Chương 2 | A | W2
W4 | JavaScript cơ bản | Chương 2 | U | W1
W5 | Thao tác DOM | Chương 2 | A | W4
W6 | Xử lý sự kiện | Chương 3 | A | W5
W7 | Gọi API bằng fetch | Chương 3 | A | W5
W8 | Giao diện đáp ứng | Chương 3 | A | W3
W9 | Biểu mẫu và kiểm tra dữ liệu | Chương 4 | A | W6
W10 | Triển khai website | Chương 4 | A | W7, W9
"""
