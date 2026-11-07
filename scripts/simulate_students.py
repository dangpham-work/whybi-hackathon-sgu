"""KT-05 – 30 SV qua API phiên thật; mặc định N5 có 9 Đạt / 21 Chưa đạt.

Chạy từ backend sau khi seed_db.py đã nạp CSDL (xem seed/README.md).
PowerShell, đặt cùng cấu hình ở terminal 1 và 2:
    $env:APP_ENV='dev'; $env:LLM_MODE='fake'; $env:DEMO_MODE='1'
    $env:DATABASE_URL='postgresql+psycopg://whybi:whybi@localhost:5432/whybi'
    $env:REDIS_URL='redis://localhost:6379/0'
Terminal 1: uv run python -m app.workers.mastery_listener
Terminal 2: uv run python ../scripts/simulate_students.py --serve-demo
Terminal 3: uv run python ../scripts/simulate_students.py --prepare-demo

--prepare-demo bổ sung rubric minh họa còn thiếu và phát hành cây nháp qua API GV.
Chỉ dùng trên CSDL demo riêng; không phải rubric chuyên môn đã được GV thẩm định.
LLM giả gốc bỏ qua transcript: server demo riêng thay provider qua LLMGateway,
giữ nguyên Guard, Judge, API, sự kiện và MasteryService. Đây là dữ liệu giả lập,
không phải số liệu đánh giá chất lượng AI (KT-07). Không có API /complete.
Chạy lại bỏ qua ô đã đúng kịch bản; dữ liệu khác kịch bản thì dừng, không xóa/ghi đè.
--pass-rate áp dụng các nút thường; --weak-pass-rate áp dụng N5. Tổ tiên của N5
luôn Đạt để cả 30 SV tiếp cận được điểm nghẽn. Nút còn khóa được bỏ qua.
"""

import argparse
import json
import math
import re
import sys
import time
from graphlib import TopologicalSorter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed"
FAIL_TEXT = "Mình chưa hiểu khái niệm này."
PASSWORD = "Whybi@2026"  # tài khoản giả công khai trong seed/README.md


class SimulationError(RuntimeError):
    """Lỗi có thể báo cho người chạy mà không in token hoặc mật khẩu."""


def plan(tree, weak_node):
    nodes = {n["key"]: n for n in tree["nodes"]}
    weak = [n for n in nodes.values() if weak_node in (n["key"], n.get("code"))]
    if len(weak) != 1:
        raise SimulationError(f"Không tìm thấy duy nhất nút {weak_node} trong cây")
    parents = {key: set() for key in nodes}
    for edge in tree["edges"]:
        if edge["fromKey"] not in nodes or edge["toKey"] not in nodes:
            raise SimulationError("Cạnh trỏ tới nút không có trong cây")
        parents[edge["toKey"]].add(edge["fromKey"])
    ordered = [nodes[key] for key in TopologicalSorter(parents).static_order()]
    ancestors, pending = set(), list(parents[weak[0]["key"]])
    while pending:
        key = pending.pop()
        if key not in ancestors:
            ancestors.add(key)
            pending.extend(parents[key])
    return ordered, weak[0], ancestors


class Simulator:
    def __init__(
        self,
        client,
        *,
        students=30,
        join_code="CTDL2026",
        pass_rate=0.6,
        weak_pass_rate=0.3,
        weak_node="N5",
        delay=0.3,
        wait_timeout=15,
    ):
        accounts = json.loads((SEED / "users.json").read_text(encoding="utf-8"))
        if not isinstance(students, int) or not 1 <= students <= len(accounts["students"]):
            raise ValueError("--students phải từ 1 đến 30")
        if any(not math.isfinite(rate) or not 0 <= rate <= 1 for rate in (pass_rate, weak_pass_rate)):
            raise ValueError("Tỉ lệ Đạt phải hữu hạn và nằm trong [0, 1]")
        if not math.isfinite(delay) or delay < 0 or not math.isfinite(wait_timeout) or wait_timeout <= 0:
            raise ValueError("--delay phải >= 0 và --wait-timeout phải > 0, hữu hạn")
        if not re.fullmatch(r"[A-Z0-9]{8}", join_code.upper()):
            raise ValueError("Mã lớp cần 8 chữ hoặc số")
        self.client, self.students = client, accounts["students"][:students]
        self.lecturer = accounts["lecturers"][0]
        self.join_code, self.weak_node = join_code.upper(), weak_node
        self.pass_rate, self.weak_pass_rate = pass_rate, weak_pass_rate
        self.delay, self.wait_timeout = delay, wait_timeout

    def request(self, method, path, token=None, *, allow_enrolled=False, allow_pending_heatmap=False, **kwargs):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = self.client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise SimulationError(f"Không kết nối được API ({type(exc).__name__}): {method} {path}") from None
        try:
            body = response.json()
        except ValueError:
            raise SimulationError(f"API không trả JSON: {method} {path} ({response.status_code})") from None
        if response.is_error:
            code = body.get("error", {}).get("code", "UNKNOWN") if isinstance(body, dict) else "UNKNOWN"
            if allow_enrolled and response.status_code == 409 and code == "ALREADY_ENROLLED":
                return None
            # Không in response body: có thể chứa dữ liệu nhạy cảm.
            if (
                allow_pending_heatmap
                and response.status_code == 501
                and code == "NOT_IMPLEMENTED"
                and body.get("error", {}).get("details", {}).get("card") == "C2-13"
            ):
                return None
            raise SimulationError(f"{method} {path}: HTTP {response.status_code} {code}")
        return body

    def login(self, account):
        return self.request(
            "POST",
            "/api/v1/auth/login",
            json={
                "email": account["email"],
                "password": PASSWORD,
            },
        )["accessToken"]

    def prepare(self, class_id, token):
        info = self.request("GET", "/openapi.json").get("info", {})
        if info.get("x-kt05-demo") is not True:
            raise SimulationError("--prepare-demo chỉ dùng với server KT-05 --serve-demo")
        tree = self.request("GET", f"/api/v1/classes/{class_id}/tree?draft=true", token)
        plan(tree, self.weak_node)
        if tree["status"] == "PUBLISHED":
            return tree
        if tree["status"] not in ("DRAFT", "EDITING"):
            raise SimulationError("Cây không phải bản nháp có thể chuẩn bị cho demo")
        for node in tree["nodes"]:
            rubric = node.get("rubric")
            if rubric and rubric.get("approved"):
                continue
            rubric = (
                dict(rubric)
                if rubric
                else {
                    "keyPoints": [{"id": "KP1", "content": f"Minh họa khái niệm {node['title']}", "isRequired": True}],
                    "minChallenges": 3,
                    "minPassedChallenges": 2,
                    "passThreshold": 70,
                    "scenarios": [],
                    "misconceptions": [],
                    "sourcePages": [],
                }
            )
            rubric["approved"] = True
            self.request("PUT", f"/api/v1/nodes/{node['id']}/rubric", token, json=rubric)
        return self.request("POST", f"/api/v1/tree-versions/{tree['id']}/publish", token)

    def my_map(self, class_id, token):
        return self.request("GET", f"/api/v1/classes/{class_id}/my-map", token)

    def wait_mastery(self, class_id, token, node, session_id, expected):
        deadline = time.monotonic() + self.wait_timeout
        while True:
            cells = self.my_map(class_id, token)["progress"]
            cell = next(c for c in cells if c["nodeId"] == node["id"])
            if cell["state"] == expected and cell.get("lastSessionId") == session_id and cell["attempts"] >= 1:
                return
            if time.monotonic() >= deadline:
                raise SimulationError(
                    f"Hết thời gian đợi MasteryService tại {node['code']}; "
                    "kiểm tra tiến trình events / mastery_listener"
                )
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))

    def session(self, class_id, token, student_id, node, passed):
        created = self.request(
            "POST",
            "/api/v1/sessions",
            token,
            json={
                "nodeId": node["id"],
                "inputMode": "TEXT",
                "ttsEnabled": False,
            },
        )
        sid, status = created["sessionId"], created["status"]
        points = (node.get("rubric") or {}).get("keyPoints", [])
        text = " ".join(point["content"] for point in points) or f"Mình giải thích về {node['title']}."
        if not passed:
            text = FAIL_TEXT + " Mình cần ôn lại và chưa giải thích được ví dụ."
        for _ in range(12):
            if status not in ("EXPLAINING", "CHALLENGING"):
                raise SimulationError(f"Phiên {sid} kết thúc bất thường: {status}")
            reply = self.request(
                "POST",
                f"/api/v1/sessions/{sid}/turns",
                token,
                json={
                    "turnType": "EXPLANATION" if status == "EXPLAINING" else "ANSWER",
                    "inputMode": "TEXT",
                    "text": text,
                },
            )
            status = reply["status"]
            if status == "COMPLETED":
                break
        else:
            raise SimulationError(f"Phiên {sid} vượt giới hạn 12 lượt; kiểm tra Guard / Tutee")
        result = self.request("GET", f"/api/v1/sessions/{sid}/result", token)
        expected = "MASTERED" if passed else "NOT_PASSED"
        if any(
            result[key] != value
            for key, value in {
                "sessionId": sid,
                "studentId": student_id,
                "classId": class_id,
                "nodeId": node["id"],
                "verdict": "PASSED" if passed else "FAILED",
                "state": expected,
            }.items()
        ):
            raise SimulationError(
                f"Kết quả {node['code']} khác kịch bản; dùng --serve-demo (LLM fake gốc không đổi theo lời giảng)"
            )
        self.wait_mastery(class_id, token, node, sid, expected)

    def run(self, prepare_demo=False):
        info = self.request("GET", "/openapi.json").get("info", {})
        if info.get("x-kt05-demo") is not True:
            raise SimulationError("Kịch bản KT-05 cần server --serve-demo để tạo kết quả Đạt/Chưa đạt xác định")
        teacher_token = self.login(self.lecturer)
        classes = self.request("GET", "/api/v1/classes", teacher_token)
        matches = [c for c in classes if c["joinCode"] == self.join_code]
        if len(matches) != 1:
            raise SimulationError("Không tìm thấy lớp mẫu; chạy scripts/seed_db.py trước")
        class_id = matches[0]["id"]
        tree = (
            self.prepare(class_id, teacher_token)
            if prepare_demo
            else self.request(
                "GET",
                f"/api/v1/classes/{class_id}/tree",
                teacher_token,
            )
        )
        if tree["status"] != "PUBLISHED":
            raise SimulationError("Cây chưa phát hành; dùng --prepare-demo trên server demo KT-05")
        ordered, weak, ancestors = plan(tree, self.weak_node)
        sessions, student_ids, expected_weak = 0, [], {}
        for index, student in enumerate(self.students):
            token = self.login(student)
            self.request("POST", "/api/v1/classes/join", token, allow_enrolled=True, json={"joinCode": self.join_code})
            mapping = self.my_map(class_id, token)
            student_id = mapping["studentId"]
            if student_id in student_ids:
                raise SimulationError("API trả cùng studentId cho nhiều tài khoản")
            student_ids.append(student_id)
            expected_weak[student_id] = (
                "MASTERED" if index < int(len(self.students) * self.weak_pass_rate) else "NOT_PASSED"
            )
            for node in ordered:
                mapping = self.my_map(class_id, token)
                if mapping["tree"]["id"] != tree["id"]:
                    raise SimulationError("Cây đã đổi trong lúc giả lập; dừng để tránh trộn phiên bản")
                cell = next(c for c in mapping["progress"] if c["nodeId"] == node["id"])
                rate = self.weak_pass_rate if node["key"] == weak["key"] else self.pass_rate
                passed = node["key"] in ancestors or index < int(len(self.students) * rate)
                expected = "MASTERED" if passed else "NOT_PASSED"
                if cell["state"] == "LOCKED":
                    if node["key"] == weak["key"] or node["key"] in ancestors:
                        raise SimulationError(f"Nút {node['code']} vẫn khóa dù đã xử lý tiên quyết")
                    continue
                if cell["state"] == expected and cell["attempts"] >= 1:
                    continue
                if cell["state"] != "AVAILABLE" or cell["attempts"] != 0 or not cell["canStart"]:
                    raise SimulationError(
                        f"Dữ liệu cũ {student['email']} / {node['code']} khác kịch bản: {cell['state']}"
                    )
                self.session(class_id, token, student_id, node, passed)
                sessions += 1
            final_map = self.my_map(class_id, token)
            final_cell = next(c for c in final_map["progress"] if c["nodeId"] == weak["id"])
            if (
                final_map["studentId"] != student_id
                or final_map["tree"]["id"] != tree["id"]
                or final_cell["state"] != expected_weak[student_id]
                or final_cell["attempts"] < 1
            ):
                raise SimulationError("Bản đồ học tập chưa có kết quả N5 đúng kịch bản")
            print(
                f"[{index + 1}/{len(self.students)}] {student['full_name']}: {weak['code']} {expected_weak[student_id]}"
            )
            if self.delay and index + 1 < len(self.students):
                time.sleep(self.delay)
        passed = sum(state == "MASTERED" for state in expected_weak.values())
        summary = {
            "students": len(student_ids),
            "sessions": sessions,
            "weakPassed": passed,
            "weakAttempted": len(student_ids),
            "weakColor": None,
            "heatmapVerified": False,
            "classId": class_id,
        }
        snapshot = self.request("GET", f"/api/v1/classes/{class_id}/heatmap", teacher_token, allow_pending_heatmap=True)
        if snapshot is None:
            print("C2-13 chưa có: đã kiểm chứng bản đồ từng SV; chưa kiểm màu heatmap.")
            return summary
        rows = {row["studentId"]: row for row in snapshot["grid"]}
        for row in rows.values():
            if "statesByKey" not in row:
                row["statesByKey"] = {weak["key"]: row["states"].get(weak["id"], "LOCKED")}
        for sid, state in expected_weak.items():
            if sid not in rows or rows[sid]["statesByKey"].get(weak["key"]) != state:
                raise SimulationError("Heatmap chưa có đủ kết quả của các SV đã giả lập")
        stat = next(n for n in snapshot["nodes"] if n["nodeId"] == weak["id"])
        passed = sum(state == "MASTERED" for state in expected_weak.values())
        class_states = [row["statesByKey"].get(weak["key"], "LOCKED") for row in rows.values()]
        if "IN_PROGRESS" in class_states:
            raise SimulationError("Nút điểm nghẽn còn phiên đang chạy; chưa thể đối chiếu số tổng hợp heatmap")
        class_passed = sum(state in ("MASTERED", "NEEDS_REVERIFY") for state in class_states)
        class_attempted = class_passed + class_states.count("NOT_PASSED")
        if stat["attemptedCount"] != class_attempted or stat["passedCount"] != class_passed:
            raise SimulationError("Số tổng hợp heatmap không khớp lưới thành thạo")
        return {
            "students": len(student_ids),
            "sessions": sessions,
            "weakPassed": passed,
            "weakAttempted": len(student_ids),
            "weakColor": stat["color"],
            "heatmapVerified": True,
            "classId": class_id,
        }


def create_demo_app():
    """Factory tường minh: API thật, provider theo kịch bản; không sửa app.main/gateway."""
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi import Depends
    from sqlalchemy.orm import Session

    from app.ai.gateway import LLMGateway
    from app.ai.providers.base import LLMResult
    from app.ai.providers.fake import FakeProvider
    from app.api.sessions import get_orchestrator
    from app.core.config import get_settings
    from app.db.session import get_db
    from app.main import create_app
    from app.services.session_orchestrator import SessionOrchestrator

    settings = get_settings()
    if settings.app_env not in ("dev", "test") or settings.llm_mode != "fake" or not settings.demo_mode:
        raise SimulationError("Server KT-05 yêu cầu APP_ENV=dev|test, LLM_MODE=fake, DEMO_MODE=1")

    class DemoProvider(FakeProvider):
        def complete(self, messages, schema, *, model="fake", temperature=0):
            result = super().complete(messages, schema, model=model, temperature=temperature)
            if schema.get("title") == "JudgeResult":
                failed = any(FAIL_TEXT in m["content"] for m in messages if m["role"] == "user")
                system = "\n".join(m["content"] for m in messages if m["role"] == "system")
                points = re.findall(r"^- (\S+) \((?:bắt buộc|phụ)\):", system, re.MULTILINE)
                data = result.data
                for criterion in data["criteria"]:
                    criterion["score"] = 30 if failed else 90
                data.update(
                    coveredPoints=[] if failed else points,
                    missingPoints=points if failed else [],
                    misconceptions=[],
                    passedChallenges=0 if failed else 5,
                    totalChallenges=5,
                    strengths=[],
                    reviewHints=[],
                )
                return LLMResult(data=data, model="fake")
            return result

    gateway = LLMGateway(primary=DemoProvider())

    def demo_orchestrator(db: Session = Depends(get_db)):
        return SessionOrchestrator(db, gateway=gateway)

    app = create_app()
    app.dependency_overrides[get_orchestrator] = demo_orchestrator
    app.openapi()["info"]["x-kt05-demo"] = True
    return app


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--class", dest="join_code", default="CTDL2026")
    parser.add_argument("--students", type=int, default=30)
    parser.add_argument("--pass-rate", type=float, default=0.6)
    parser.add_argument("--weak-pass-rate", type=float, default=0.3)
    parser.add_argument("--weak-node", default="N5")
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--wait-timeout", type=float, default=15)
    parser.add_argument("--prepare-demo", action="store_true")
    parser.add_argument("--serve-demo", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.serve_demo:
            import uvicorn

            uvicorn.run(create_demo_app(), host="127.0.0.1", port=args.port)
        else:
            with httpx.Client(base_url=args.base.rstrip("/"), timeout=30) as client:
                simulator = Simulator(
                    client,
                    students=args.students,
                    join_code=args.join_code,
                    pass_rate=args.pass_rate,
                    weak_pass_rate=args.weak_pass_rate,
                    weak_node=args.weak_node,
                    delay=args.delay,
                    wait_timeout=args.wait_timeout,
                )
                print(json.dumps(simulator.run(prepare_demo=args.prepare_demo), ensure_ascii=False))
    except (SimulationError, ValueError, KeyError, StopIteration, TypeError) as exc:
        message = (
            str(exc) if isinstance(exc, (SimulationError, ValueError)) else "API trả dữ liệu thiếu hoặc sai hợp đồng"
        )
        print(f"KT-05 thất bại: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
