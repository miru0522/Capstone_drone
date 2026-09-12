import { useEffect, useRef, useState } from 'react';
import { RANGE_PRESETS, rangeLabel } from '../../utils/time';

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const pad = (n) => String(n).padStart(2, '0');
/** 로컬(한국) 날짜를 'YYYY-MM-DD'로. 문자열 비교로 앞뒤를 가릴 수 있다. */
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const firstOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);

/**
 * 기간 선택. 미리 정한 범위 6개 + 달력으로 날짜 범위.
 *
 * value: { preset: '7d' } 또는 { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' } (양 끝 포함)
 *
 * - 미리 정한 범위는 누르면 바로 적용된다.
 * - 달력은 시작일·종료일을 차례로 누르고 「적용」해야 바뀐다. 하루만 고르면 그날 하루.
 * - 바깥을 누르거나 Esc 면 취소. 미래 날짜는 고를 수 없다.
 * - 타이핑 입력은 두지 않는다 — 관제사에게 "3h" 같은 형식은 낯설다(2026-09-10 결정).
 */
export default function DateRangePicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ start: null, end: null });
  const [hover, setHover] = useState(null);
  const [month, setMonth] = useState(() => firstOfMonth(new Date()));
  const rootRef = useRef(null);

  const today = ymd(new Date());

  const openPicker = () => {
    // 이미 날짜 범위를 골라 둔 상태면 그 범위와 그 달에서 연다
    if (value.start) {
      setDraft({ start: value.start, end: value.end });
      const [y, m] = value.start.split('-').map(Number);
      setMonth(new Date(y, m - 1, 1));
    } else {
      setDraft({ start: null, end: null });
      setMonth(firstOfMonth(new Date()));
    }
    setHover(null);
    setOpen(true);
  };

  // 바깥을 누르거나 Esc 면 취소
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const pickPreset = (key) => {
    onChange({ preset: key });
    setOpen(false);
  };

  const pickDay = (d) => {
    // 시작일이 없거나 이미 범위가 완성돼 있으면 새로 시작한다
    if (!draft.start || draft.end) {
      setDraft({ start: d, end: null });
      return;
    }
    setDraft(d < draft.start ? { start: d, end: draft.start } : { start: draft.start, end: d });
  };

  const apply = () => {
    onChange({ start: draft.start, end: draft.end ?? draft.start });
    setOpen(false);
  };

  // 달력 칸
  const y = month.getFullYear();
  const m = month.getMonth();
  const lead = new Date(y, m, 1).getDay();
  const days = new Date(y, m + 1, 0).getDate();
  const cells = [
    ...Array(lead).fill(null),
    ...Array.from({ length: days }, (_, i) => ymd(new Date(y, m, i + 1))),
  ];
  const canNext = ymd(new Date(y, m + 1, 1)) <= today;

  // 종료일을 아직 안 골랐으면 마우스가 올라간 날까지 미리 칠한다
  const tail = draft.end ?? (draft.start && hover ? hover : null);
  const lo = draft.start && tail ? (tail < draft.start ? tail : draft.start) : draft.start;
  const hi = draft.start && tail ? (tail < draft.start ? draft.start : tail) : draft.start;

  const dayClass = (d) => {
    if (d > today) return 'text-gray-300 cursor-not-allowed';
    if (d === lo || d === hi) return 'bg-[#0058be] text-white font-bold cursor-pointer';
    if (lo && hi && d > lo && d < hi) return 'bg-[#e5eeff] text-[#0058be] cursor-pointer';
    return `text-gray-700 hover:bg-gray-100 cursor-pointer ${d === today ? 'font-bold ring-1 ring-inset ring-[#0058be]/40' : ''}`;
  };

  const draftText = !draft.start
    ? '시작일을 고르세요'
    : !draft.end
      ? `${rangeLabel({ start: draft.start, end: draft.start })} — 종료일을 고르세요`
      : rangeLabel(draft);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : openPicker())}
        // 폭을 고정한다 — 「최근 7일」↔「9월 3일 – 9월 10일」처럼 글자가 바뀌어도 옆이 밀리지 않게.
        // 가장 긴 경우(올해가 아닌 범위)는 말줄임되고, 전체는 title 로 보인다.
        className="w-[236px] flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white hover:bg-gray-50 cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
        title={rangeLabel(value)}
      >
        <span className="material-symbols-outlined text-[18px] text-gray-500 shrink-0">calendar_month</span>
        <span className="flex-1 min-w-0 truncate text-left font-medium text-gray-800">{rangeLabel(value)}</span>
        <span className="material-symbols-outlined text-[18px] text-gray-400 shrink-0">{open ? 'expand_less' : 'expand_more'}</span>
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-2 z-50 flex bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
          {/* 미리 정한 범위 — 누르면 바로 적용 */}
          <ul className="w-36 border-r border-gray-100 py-2 shrink-0">
            {RANGE_PRESETS.map((p) => (
              <li key={p.key}>
                <button
                  type="button"
                  onClick={() => pickPreset(p.key)}
                  className={`w-full text-left px-4 py-2 text-sm transition-colors cursor-pointer ${
                    value.preset === p.key
                      ? 'bg-[#e5eeff] text-[#0058be] font-bold'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {p.label}
                </button>
              </li>
            ))}
          </ul>

          {/* 달력 — 두 번 눌러 범위를 잡고 「적용」 */}
          <div className="p-4 w-[296px]">
            <div className="flex items-center justify-between mb-3">
              <button
                type="button"
                onClick={() => setMonth(new Date(y, m - 1, 1))}
                className="p-1 rounded-lg text-gray-600 hover:bg-gray-100 cursor-pointer"
                aria-label="이전 달"
              >
                <span className="material-symbols-outlined text-[20px]">chevron_left</span>
              </button>
              <span className="text-sm font-bold text-gray-800">{y}년 {m + 1}월</span>
              <button
                type="button"
                onClick={() => canNext && setMonth(new Date(y, m + 1, 1))}
                disabled={!canNext}
                className="p-1 rounded-lg text-gray-600 hover:bg-gray-100 cursor-pointer disabled:text-gray-300 disabled:hover:bg-transparent disabled:cursor-not-allowed"
                aria-label="다음 달"
              >
                <span className="material-symbols-outlined text-[20px]">chevron_right</span>
              </button>
            </div>

            <div className="grid grid-cols-7 mb-1">
              {WEEKDAYS.map((w, i) => (
                <span
                  key={w}
                  className={`text-center text-[11px] font-semibold ${i === 0 ? 'text-red-400' : i === 6 ? 'text-blue-400' : 'text-gray-400'}`}
                >
                  {w}
                </span>
              ))}
            </div>

            <div className="grid grid-cols-7 gap-y-1" onMouseLeave={() => setHover(null)}>
              {cells.map((d, i) =>
                d ? (
                  <button
                    key={d}
                    type="button"
                    disabled={d > today}
                    onClick={() => pickDay(d)}
                    onMouseEnter={() => setHover(d)}
                    className={`h-9 rounded-lg text-sm transition-colors ${dayClass(d)}`}
                  >
                    {Number(d.slice(8))}
                  </button>
                ) : (
                  <span key={`blank-${i}`} />
                ),
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between gap-2">
              <span className="text-xs text-gray-500 truncate">{draftText}</span>
              <div className="flex gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold text-gray-600 hover:bg-gray-100 cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="button"
                  onClick={apply}
                  disabled={!draft.start}
                  className="px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-[#0058be] hover:bg-[#00479b] cursor-pointer disabled:bg-gray-300 disabled:cursor-not-allowed"
                >
                  적용
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
