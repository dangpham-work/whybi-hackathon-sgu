import { Check, ChevronDown, Clock, History, Play, Sparkles, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { AsyncView, ErrorBox } from "../../components/AsyncView";
import { Button } from "../../components/Button";
import { apiCall, errorText } from "../../lib/api";
import { MATCH_STATUS, remaining, type MatchOut } from "../../lib/matching";
import { useApi } from "../../lib/useApi";

function formatDateTime(iso?: string | null) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

/** SV-07 Bạn cùng tiến (Figma 25:1602, FR-PM-01, 05, 06, 07, GD-11).
 * Sinh viên xem thông tin bạn được giảng viên ghép cặp theo từng lớp.
 * Sinh viên không có quyền chọn chấp nhận/từ chối hay bật/tắt ghép cặp;
 * ô chính hiển thị ghép cặp mới nhất kèm thời gian giảng viên ghép,
 * có tab sổ xuống xem lịch sử các lần ghép trước.
 */
export default function StudentPeers() {
  const { classId: routeClassId = "" } = useParams();
  const classes = useApi((signal) => apiCall("get", "/classes", { signal }).catch(() => []), []);
  const cls = useApi(
    (signal) => (routeClassId ? apiCall("get", "/classes/{class_id}", { path: { class_id: routeClassId }, signal }).catch(() => null) : Promise.resolve(null)),
    [routeClassId]
  );

  const [selectedClassId, setSelectedClassId] = useState<string>(routeClassId);

  useEffect(() => {
    if (routeClassId) {
      setSelectedClassId(routeClassId);
    } else if (classes.data && classes.data.length > 0 && !selectedClassId) {
      setSelectedClassId(classes.data[0].id);
    }
  }, [routeClassId, classes.data, selectedClassId]);

  const activeId = selectedClassId || routeClassId;
  const classList = classes.data ?? [];
  const currentClass = classList.find((c) => c.id === activeId) ?? cls.data;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-h1 font-bold">Bạn cùng tiến</h1>
        <p className="text-body-m text-ink-500">
          Xem thông tin bạn học được giảng viên ghép cặp để cùng tiến bộ.
        </p>
      </div>

      {classList.length > 1 && (
        <div role="tablist" aria-label="Chọn lớp học phần" className="flex flex-wrap gap-2 border-b border-line-soft pb-3">
          {classList.map((c) => {
            const active = c.id === activeId;
            return (
              <button
                key={c.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setSelectedClassId(c.id)}
                className={`rounded-full px-3.5 py-1.5 text-body-s font-semibold transition ${
                  active
                    ? "bg-teal text-white shadow-sm"
                    : "border border-line-strong bg-surface text-ink-700 hover:bg-app"
                }`}
              >
                {c.name} ({c.semester})
              </button>
            );
          })}
        </div>
      )}

      {activeId ? (
        <ClassPeerDetail key={activeId} classId={activeId} className={currentClass?.name} semester={currentClass?.semester} />
      ) : (
        <p className="text-body-m text-ink-500">Bạn chưa chọn hoặc chưa tham gia lớp học phần nào.</p>
      )}
    </div>
  );
}

/** Chi tiết ghép cặp cho một lớp học phần cụ thể */
function ClassPeerDetail({ classId, className, semester }: { classId: string; className?: string; semester?: string }) {
  const matches = useApi(
    (signal) => apiCall("get", "/classes/{class_id}/matches", { path: { class_id: classId }, signal }),
    [classId]
  );
  const map = useApi(
    (signal) => apiCall("get", "/classes/{class_id}/my-map", { path: { class_id: classId }, signal }),
    [classId]
  );
  const [showHistory, setShowHistory] = useState(false);

  const title = (key: string) => map.data?.tree.nodes.find((n) => n.key === key)?.title ?? key;
  const nodeId = (key: string) => map.data?.tree.nodes.find((n) => n.key === key)?.id ?? undefined;

  return (
    <div className="space-y-4">
      {className && (
        <div className="rounded-lg border border-line-soft bg-surface px-4 py-2.5">
          <p className="text-body-m font-semibold text-teal">
            Lớp: {className} {semester ? `(${semester})` : ""}
          </p>
        </div>
      )}

      <AsyncView state={matches}>
        {(list) => {
          if (list.length === 0) {
            return (
              <div role="status" className="space-y-2 rounded-xl border border-line-soft bg-surface p-6 text-center">
                <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-st-grey text-ink-500">
                  <Users size={24} />
                </div>
                <h2 className="text-h3 font-bold text-ink-700">Chưa được ghép cặp</h2>
                <p className="mx-auto max-w-sm text-body-m text-ink-500">
                  Bạn chưa được giảng viên ghép cặp trong lớp học này. Khi giảng viên chạy vòng ghép cặp, thông tin bạn cùng tiến sẽ xuất hiện tại đây.
                </p>
              </div>
            );
          }

          const latest = list[0];
          const history = list.slice(1);

          return (
            <div className="space-y-4">
              {/* Ô chính: Cặp ghép mới nhất */}
              <section aria-label="Ghép cặp mới nhất">
                <MainMatchCard
                  m={latest}
                  title={title}
                  nodeId={nodeId}
                  myId={map.data?.studentId}
                  onChanged={matches.reload}
                />
              </section>

              {/* Tab sổ xuống xem lịch sử ghép cặp */}
              <section aria-label="Lịch sử ghép cặp" className="overflow-hidden rounded-xl border border-line-soft bg-surface">
                <button
                  type="button"
                  aria-expanded={showHistory}
                  onClick={() => setShowHistory((prev) => !prev)}
                  className="flex w-full items-center justify-between p-4 text-left font-semibold hover:bg-app"
                >
                  <span className="flex items-center gap-2 text-h3 font-bold">
                    <History aria-hidden size={18} className="text-teal" />
                    Lịch sử ghép cặp {history.length > 0 ? `(${history.length})` : ""}
                  </span>
                  <ChevronDown
                    aria-hidden
                    size={20}
                    className={`text-ink-500 transition-transform duration-200 ${showHistory ? "rotate-180" : ""}`}
                  />
                </button>

                {showHistory && (
                  <div className="space-y-3 border-t border-line-soft bg-app/50 p-4">
                    {history.length === 0 ? (
                      <p className="py-2 text-center text-body-m text-ink-500">
                        Chưa có lịch sử các lần ghép cặp trước đây trong lớp này.
                      </p>
                    ) : (
                      <ul aria-label="Danh sách lịch sử ghép cặp" className="space-y-3">
                        {history.map((m) => (
                          <li key={m.id}>
                            <HistoryMatchCard
                              m={m}
                              title={title}
                              nodeId={nodeId}
                              myId={map.data?.studentId}
                            />
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </section>
            </div>
          );
        }}
      </AsyncView>
    </div>
  );
}

/** Thẻ hiển thị cặp mới nhất ở ô chính */
function MainMatchCard({
  m,
  title,
  nodeId,
  myId,
  onChanged,
}: {
  m: MatchOut;
  title: (k: string) => string;
  nodeId: (k: string) => string | undefined;
  myId?: string;
  onChanged: () => void;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>();
  const look = MATCH_STATUS[m.status] ?? MATCH_STATUS.PROPOSED;
  const Icon = look.icon;

  async function actStudied() {
    setBusy(true);
    setFailure(undefined);
    try {
      await apiCall("post", "/matches/{match_id}/{action}", { path: { match_id: m.id, action: "studied" } });
      onChanged();
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  }

  async function verify(itemId: string, key: string) {
    const node = nodeId(key);
    if (!node) return;
    setBusy(true);
    try {
      const s = await apiCall("post", "/sessions", {
        body: { nodeId: node, inputMode: "TEXT", ttsEnabled: false, peerMatchItemId: itemId },
      });
      navigate(`/sv/sessions/${s.sessionId}`, { state: { opening: s.opening } });
    } catch (e) {
      setFailure(e);
      setBusy(false);
    }
  }

  const myItems = m.items.filter((i) => i.learnerId === myId && !i.verified);
  const isOneWay = m.oneWay;

  return (
    <article className="space-y-3 rounded-xl border border-teal/40 bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft pb-3">
        <div className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-full bg-teal-soft text-teal">
            <Sparkles aria-hidden size={16} />
          </span>
          <h2 className="text-h3 font-bold text-ink-900">Cặp bạn cùng tiến hiện tại</h2>
        </div>
        <div className="flex items-center gap-1.5">
          {isOneWay && (
            <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-body-s font-semibold text-blue-800">
              Ghép 1 chiều (kiểm tra bài cũ)
            </span>
          )}
          <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-body-s font-semibold ${look.className}`}>
            <Icon aria-hidden size={12} /> {look.label}
          </span>
        </div>
      </div>

      <div>
        <p className="text-h2 font-bold text-ink-900">{m.partnerName}</p>
        {m.partnerEmail && <p className="text-body-s text-teal">{m.partnerEmail}</p>}
        {m.createdAt && (
          <p className="mt-1 flex items-center gap-1 text-body-s text-ink-500">
            <Clock aria-hidden size={13} />
            Được giảng viên ghép: <span className="font-medium text-ink-700">{formatDateTime(m.createdAt)}</span>
          </p>
        )}
        {["PROPOSED", "WAITING_OTHER", "ACCEPTED", "STUDIED"].includes(m.status) && (
          <p className="text-body-s text-ink-500">Hạn: {remaining(m.expiresAt)}</p>
        )}
      </div>

      <div className="space-y-2 pt-1">
        <Section label={`Bạn sẽ dạy ${m.partnerName.split(" ").at(-1)}`} keys={m.iTeach} title={title} tone="pass" />
        <Section label={`${m.partnerName.split(" ").at(-1)} sẽ dạy bạn`} keys={m.iLearn} title={title} tone="fail" />
      </div>

      {failure !== undefined && <ErrorBox text={errorText(failure)} />}

      <div className="pt-2">
        {!m.studiedByMe && (
          <div className="space-y-1">
            <Button className="w-full" disabled={busy} onClick={actStudied}>
              <Check aria-hidden size={16} /> Đã học cùng
            </Button>
            <p className="text-center text-body-s text-ink-500">
              Bấm xác nhận sau khi bạn và bạn cùng tiến đã hoàn thành buổi học đôi.
            </p>
          </div>
        )}

        {["STUDIED", "PARTIALLY_VERIFIED"].includes(m.status) &&
          myItems.map((i) => (
            <Button key={i.id} variant="teal" className="mt-2 w-full" disabled={busy} onClick={() => verify(i.id, i.nodeKey)}>
              <Play aria-hidden size={16} /> Giảng lại {title(i.nodeKey)} để xác nhận
            </Button>
          ))}
      </div>
    </article>
  );
}

/** Thẻ hiển thị các cặp trong lịch sử ghép cặp */
function HistoryMatchCard({
  m,
  title,
  nodeId,
  myId,
}: {
  m: MatchOut;
  title: (k: string) => string;
  nodeId: (k: string) => string | undefined;
  myId?: string;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const look = MATCH_STATUS[m.status] ?? MATCH_STATUS.PROPOSED;
  const Icon = look.icon;

  async function verify(itemId: string, key: string) {
    const node = nodeId(key);
    if (!node) return;
    setBusy(true);
    try {
      const s = await apiCall("post", "/sessions", {
        body: { nodeId: node, inputMode: "TEXT", ttsEnabled: false, peerMatchItemId: itemId },
      });
      navigate(`/sv/sessions/${s.sessionId}`, { state: { opening: s.opening } });
    } catch {
      setBusy(false);
    }
  }

  const myItems = m.items.filter((i) => i.learnerId === myId && !i.verified);

  return (
    <div className="space-y-2 rounded-lg border border-line-soft bg-surface p-3.5 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-body-m font-bold text-ink-900">{m.partnerName}</p>
          {m.createdAt && (
            <p className="text-body-s text-ink-500">
              Được giảng viên ghép: {formatDateTime(m.createdAt)}
            </p>
          )}
        </div>
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-body-s font-semibold ${look.className}`}>
          <Icon aria-hidden size={12} /> {look.label}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-1 text-body-s sm:grid-cols-2">
        {m.iTeach.length > 0 && (
          <p className="text-ink-700">
            <span className="font-semibold text-green-800">Dạy:</span> {m.iTeach.map(title).join(", ")}
          </p>
        )}
        {m.iLearn.length > 0 && (
          <p className="text-ink-700">
            <span className="font-semibold text-red-800">Học:</span> {m.iLearn.map(title).join(", ")}
          </p>
        )}
      </div>

      {["STUDIED", "PARTIALLY_VERIFIED"].includes(m.status) &&
        myItems.map((i) => (
          <Button key={i.id} variant="teal" className="mt-1 w-full" disabled={busy} onClick={() => verify(i.id, i.nodeKey)}>
            <Play aria-hidden size={14} /> Giảng lại {title(i.nodeKey)} để xác nhận
          </Button>
        ))}
    </div>
  );
}

function Section({
  label,
  keys,
  title,
  tone,
}: {
  label: string;
  keys: string[];
  title: (k: string) => string;
  tone: "pass" | "fail";
}) {
  if (keys.length === 0) return null;
  return (
    <div className="space-y-1">
      <p className="text-body-s font-medium text-ink-500">→ {label}</p>
      {keys.map((k) => (
        <p
          key={k}
          className={`rounded-md px-3 py-1.5 text-body-m font-semibold ${
            tone === "pass" ? "bg-st-pass text-green-900" : "bg-st-fail text-red-900"
          }`}
        >
          {title(k)}
        </p>
      ))}
    </div>
  );
}
