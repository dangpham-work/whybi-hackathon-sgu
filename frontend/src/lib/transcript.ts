/** Ngưỡng độ tin cậy STT (STT_MIN_CONFIDENCE ở backend, C1-12). */
export const STT_THRESHOLD = 0.8;
/** Sửa quá tỉ lệ này so với bản gốc coi là viết lại nội dung (FR-TB-07: chỉ cho sửa lỗi nhận dạng). */
export const MAX_EDIT_RATIO = 0.2;

/** Khoảng cách Levenshtein theo từ (tách theo khoảng trắng) – đủ để đo mức sửa của một đoạn lời giảng. */
function wordDistance(a: string[], b: string[]): number {
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return prev[b.length];
}

const words = (s: string) => s.trim().split(/\s+/).filter(Boolean);

/** Tỉ lệ từ bị sửa so với bản gốc, 0 = giữ nguyên. */
export function editRatio(original: string, edited: string): number {
  const a = words(original);
  if (a.length === 0) return edited.trim() ? 1 : 0;
  return wordDistance(a, words(edited)) / a.length;
}

/** Tách văn bản thành các đoạn, đánh dấu từ nằm trong danh sách không chắc chắn (so không phân biệt hoa thường, bỏ dấu câu). */
export function markUncertain(text: string, uncertain: string[]): { text: string; uncertain: boolean }[] {
  const norm = (w: string) => w.toLowerCase().replace(/[.,;:!?()"“”]/g, "");
  const set = new Set(uncertain.map(norm));
  return text.split(/(\s+)/).map((part) => ({ text: part, uncertain: !!part.trim() && set.has(norm(part)) }));
}
