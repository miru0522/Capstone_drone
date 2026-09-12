/**
 * 서버 시각 다루기.
 *
 * 서버(백엔드 컨테이너·DB)는 UTC로 저장하고, 시각을 시간대 표기 없이
 * "2026-09-11T03:48:12.669186" 처럼 보낸다. 브라우저는 표기가 없으면 로컬(한국)
 * 시간으로 읽으므로, 그대로 new Date() 하면 9시간 이르게 보인다(2026-09-11 확인).
 *
 * 서버 시각은 반드시 parseServerTime 으로 읽고, 서버로 보낼 구간도 여기서 만든다.
 */

const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i;

/** 서버가 보낸 시각을 Date로. 시간대 표기가 없으면 UTC로 본다. 없으면 null. */
export const parseServerTime = (v) => {
  if (v == null || v === '') return null;
  if (v instanceof Date || typeof v === 'number') return new Date(v);
  // 소수 초는 6자리까지 오는데, 표준이 보장하는 것은 3자리까지다.
  const s = String(v).replace(/(\.\d{3})\d+/, '$1');
  return new Date(HAS_ZONE.test(s) ? s : `${s}Z`);
};

/** Date를 서버 매개변수 형식(UTC, 시간대 표기 없음)으로. 서버의 LocalDateTime 과 같은 기준이다. */
export const toServerTime = (d) => d.toISOString().slice(0, 19);

// ── 조회 기간 ───────────────────────────────────────────────
// 기간은 { preset: '7d' } 또는 { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }(양 끝 포함, 한국 날짜).

export const RANGE_PRESETS = [
  { key: '1h', label: '최근 1시간', ms: 3_600_000 },
  { key: '6h', label: '최근 6시간', ms: 6 * 3_600_000 },
  { key: '24h', label: '최근 24시간', ms: 24 * 3_600_000 },
  { key: '7d', label: '최근 7일', ms: 7 * 86_400_000 },
  { key: '30d', label: '최근 30일', ms: 30 * 86_400_000 },
  { key: 'all', label: '전체 기간', ms: null },
];

/** 세 탭이 함께 쓰는 기본 기간 */
export const DEFAULT_RANGE = { preset: '7d' };

const ymdToLocal = (s, addDays = 0) => {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d + addDays);
};

/**
 * 기간을 서버 구간 { from, to }(UTC)로. 「최근 N」은 부르는 순간 기준이다.
 *
 * - 「최근 N」·「전체」의 끝은 하루 뒤로 넉넉히 잡는다. 서버 시계가 브라우저와 다르면
 *   (2026-09-11 기준 5분 늦다) 끝을 "지금"으로 자를 때 방금 쌓인 행이 빠질 수 있다.
 * - 「전체」도 시작을 명시한다. 비행 목록은 from·to 가 둘 다 있어야 구간으로 조회한다.
 * - 날짜 범위는 한국 날짜 기준 — 시작일 00:00 ~ 종료일 다음 날 00:00.
 */
export const rangeToServer = (range, now = new Date()) => {
  if (range.preset) {
    const p = RANGE_PRESETS.find((x) => x.key === range.preset);
    const from = p?.ms == null ? new Date(2000, 0, 1) : new Date(now.getTime() - p.ms);
    return { from: toServerTime(from), to: toServerTime(new Date(now.getTime() + 86_400_000)) };
  }
  return { from: toServerTime(ymdToLocal(range.start)), to: toServerTime(ymdToLocal(range.end, 1)) };
};

/** 사고 영상·음성 보존 기간. ⚠️ 백엔드 app.media.retention.days 와 같아야 한다. */
export const MEDIA_RETENTION_DAYS = 365;

/** 보존 기간이 지난 사고인가 — 영상이 없을 때 "원래 없음"과 "기간이 지나 지움"을 가른다. */
export const isPastMediaRetention = (serverTime) => {
  const t = parseServerTime(serverTime);
  return t != null && Date.now() - t.getTime() > MEDIA_RETENTION_DAYS * 86_400_000;
};

/** 버튼에 보일 이름. 올해가 아니면 연도를 붙인다. */
export const rangeLabel = (range) => {
  if (range.preset) return RANGE_PRESETS.find((p) => p.key === range.preset)?.label ?? '';
  const fmt = (s) => {
    const [y, m, d] = s.split('-').map(Number);
    return `${y !== new Date().getFullYear() ? `${y}년 ` : ''}${m}월 ${d}일`;
  };
  return range.start === range.end ? fmt(range.start) : `${fmt(range.start)} – ${fmt(range.end)}`;
};

// ── 화면 표기 ───────────────────────────────────────────────
// 시각은 초까지 보인다 — 언제 일어났는지가 초동 대처의 근거다(2026-09-11 결정).

const pad2 = (n) => String(n).padStart(2, '0');
const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
const valid = (d) => d != null && !Number.isNaN(d.getTime());

/** 표에 쓰는 시각 — 26.09.11 14:30:12 */
export const fmtDateTime = (v) => {
  const d = parseServerTime(v);
  if (!valid(d)) return '-';
  return `${String(d.getFullYear()).slice(2)}.${pad2(d.getMonth() + 1)}.${pad2(d.getDate())} `
    + `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
};

/** 시각만 — 14:30:12 */
export const fmtClock = (v) => {
  const d = parseServerTime(v);
  if (!valid(d)) return '-';
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
};

/** 날짜 묶음 머리 — 9월 11일 (목). 올해가 아니면 연도를 붙인다. Date 를 받는다. */
export const fmtDayHeader = (d) => {
  if (!valid(d)) return '-';
  const year = d.getFullYear() !== new Date().getFullYear() ? `${d.getFullYear()}년 ` : '';
  return `${year}${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEK[d.getDay()]})`;
};
