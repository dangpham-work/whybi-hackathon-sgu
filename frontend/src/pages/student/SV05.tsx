import { Navigate, useParams } from "react-router";

/** SV-05 là bảng xác nhận hiện ngay trong phiên giảng (components/TranscriptConfirm, GD-08); mở thẳng đường dẫn này thì quay về phiên. */
export default function StudentTranscript() {
  const { sessionId = "" } = useParams();
  return <Navigate to={`/sv/sessions/${sessionId}`} replace />;
}
