import { Check, Info, Play, Sparkles, Users, X } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText } from "../../lib/api";
import { MATCH_STATUS, remaining, type MatchOut } from "../../lib/matching";
import { useApi } from "../../lib/useApi";

/** SV-07 Bạn cùng tiến (Figma 25:1602, FR-PM-01, 05, 06, 07, GD-11). */
export default function StudentPeers() {
  const { classId = "" } = useParams();
  const matches = useApi((signal) => apiCall("get", "/classes/{class_id}/matches", { path: { class_id: classId }, signal }), [classId]);
  const map = useApi((signal) => apiCall("get", "/classes/{class_id}/my-map", { path: { class_id: classId }, signal }), [classId]);
  const title = (key: string) => map.data?.tree.nodes.find((n) => n.key === key)?.title ?? key;
  const nodeId = (key: string) => map.data?.tree.nodes.find((n) => n.key === key)?.id ?? undefined;

  return (
    <div className="space-y-4">
      <h1 className="text-h1 font-bold">Bạn cùng tiến</h1>
      <OptInCard />
      <AsyncView state={matches} isEmpty={(l) => l.length === 0} empty="Chưa có gợi ý nào. Khi giảng viên chạy vòng ghép cặp, gợi ý sẽ hiện ở đây.">
        {(list) => (
          <ul aria-label="Cặp bạn cùng tiến" className="space-y-3">
            {list.map((m) => (
              <li key={m.id}>
                <MatchCard m={m} title={title} nodeId={nodeId} myId={map.data?.studentId} onChanged={matches.reload} />
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
    </div>
  );
}

/** Công tắc tham gia ghép cặp (FR-PM-01, BR-10). API cần `enrollmentId` nhưng backend chưa trả nó cho SV nên chưa bật được. */
function OptInCard() {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-line-soft bg-surface p-4">
      <div>
        <p className="flex items-center gap-2 font-semibold">
          <Users aria-hidden size={16} className="text-teal" /> Tham gia ghép cặp
        </p>
        <p className="text-body-s text-ink-500">Bạn có thể tắt bất cứ lúc nào (BR-10).</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked="true"
        aria-label="Tham gia ghép cặp"
        disabled
        title="Chờ API trả enrollmentId cho sinh viên (C2-14)"
        className="h-6 w-11 shrink-0 rounded-full bg-teal opacity-50"
      />
    </div>
  );
}

function MatchCard({ m, title, nodeId, myId, onChanged }: { m: MatchOut; title: (k: string) => string; nodeId: (k: string) => string | undefined; myId?: string; onChanged: () => void }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  const look = MATCH_STATUS[m.status];
  const Icon = look.icon;
  const proposed = m.status === "PROPOSED";

  async function act(action: "accept" | "decline" | "studied") {
    setBusy(true);
    setFailure(undefined);
    try {
      await apiCall("post", "/matches/{match_id}/{action}", { path: { match_id: m.id, action } });
      onChanged();
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  }

  /** Giảng lại nút bạn vừa học cùng để được xác nhận (BR-09): phiên gắn với mục dạy–học của mình. */
  async function verify(itemId: string, key: string) {
    const node = nodeId(key);
    if (!node) return;
    setBusy(true);
    try {
      const s = await apiCall("post", "/sessions", { body: { nodeId: node, inputMode: "TEXT", ttsEnabled: false, peerMatchItemId: itemId } });
      navigate(`/sv/sessions/${s.sessionId}`, { state: { opening: s.opening } });
    } catch (e) {
      setFailure(e);
      setBusy(false);
    }
  }
  const myItems = m.items.filter((i) => i.learnerId === myId && !i.verified);

  return (
    <article className={`space-y-3 rounded-xl border p-4 ${proposed ? "border-honey bg-surface" : "border-line-soft bg-surface"}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold text-honey-deep">
          {proposed && <Sparkles aria-hidden size={16} />} {proposed ? "Gợi ý mới" : "Cặp của bạn"}
        </h2>
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-body-s font-semibold ${look.className}`}>
          <Icon aria-hidden size={12} /> {look.label}
        </span>
      </div>
      <p className="text-h3 font-semibold">{m.partnerName}</p>
      {m.partnerEmail && <p className="text-body-s text-ink-500">{m.partnerEmail}</p>}
      <p className="text-body-s text-ink-500">{["PROPOSED", "WAITING_OTHER", "ACCEPTED", "STUDIED"].includes(m.status) ? `Hạn: ${remaining(m.expiresAt)}` : ""}</p>

      <Section label={`Bạn sẽ dạy ${m.partnerName.split(" ").at(-1)}`} keys={m.iTeach} title={title} tone="pass" />
      {m.oneWay ? null : <Section label={`${m.partnerName.split(" ").at(-1)} sẽ dạy bạn`} keys={m.iLearn} title={title} tone="fail" />}

      {failure !== undefined && <ErrorBox text={errorText(failure)} />}
      {proposed && !m.acceptedByMe && (
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" disabled={busy} onClick={() => act("decline")}>
            <X aria-hidden size={16} /> Từ chối
          </Button>
          <Button disabled={busy} onClick={() => act("accept")}>
            <Check aria-hidden size={16} /> Chấp nhận
          </Button>
        </div>
      )}
      {m.status === "WAITING_OTHER" && <p className="flex items-center gap-2 text-body-s text-ink-500"><Info aria-hidden size={14} /> Bạn đã chấp nhận – chờ bạn cùng tiến phản hồi.</p>}
      {m.status === "ACCEPTED" && !m.studiedByMe && (
        <Button className="w-full" disabled={busy} onClick={() => act("studied")}>
          <Check aria-hidden size={16} /> Đã học cùng
        </Button>
      )}
      {["STUDIED", "PARTIALLY_VERIFIED"].includes(m.status) &&
        myItems.map((i) => (
          <Button key={i.id} variant="teal" className="w-full" disabled={busy} onClick={() => verify(i.id, i.nodeKey)}>
            <Play aria-hidden size={16} /> Giảng lại {title(i.nodeKey)} để xác nhận
          </Button>
        ))}
    </article>
  );
}

function Section({ label, keys, title, tone }: { label: string; keys: string[]; title: (k: string) => string; tone: "pass" | "fail" }) {
  if (keys.length === 0) return null;
  return (
    <div className="space-y-1">
      <p className="text-body-s text-ink-500">→ {label}</p>
      {keys.map((k) => (
        <p key={k} className={`rounded-md px-3 py-2 font-semibold ${tone === "pass" ? "bg-st-pass text-green-900" : "bg-st-fail text-red-900"}`}>
          {title(k)}
        </p>
      ))}
    </div>
  );
}
