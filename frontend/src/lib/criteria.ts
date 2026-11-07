import type { Schema } from "./api";

/** Nhãn 5 tiêu chí Judge (Bảng 6.4). */
export const CRITERION_LABEL: Record<Schema<"CriterionCode">, string> = {
  CORRECTNESS: "Đúng đắn",
  COVERAGE: "Bao phủ ý chính",
  ESSENCE: "Bản chất – vì sao",
  ROBUSTNESS: "Đứng vững trước phản biện",
  CLARITY: "Diễn đạt mạch lạc",
};

/** Cờ vi phạm / liêm chính (FlagType) hiển thị cho GV. */
export const FLAG_LABEL: Record<Schema<"FlagType">, string> = {
  PASTE_SUSPECTED: "Dán văn bản dài bất thường",
  JAILBREAK: "Cố tình qua mặt hệ thống (jailbreak)",
  OFF_TOPIC: "Lạc đề",
  LOW_STT_CONFIDENCE: "Bản chép lời có độ tin cậy thấp",
  ANSWER_LEAK: "Câu hỏi của Whybi có nguy cơ lộ đáp án",
  GUARD_UNCHECKED: "Guard chưa kiểm được lượt này",
};
