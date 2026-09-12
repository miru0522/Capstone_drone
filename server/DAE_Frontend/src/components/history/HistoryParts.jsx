import { droneColor } from '../../utils/droneColor';
import { statusInfo } from '../../utils/incidentStatus';

/**
 * History 화면들이 함께 쓰는 조각.
 * 비행·사고·조작 세 탭과 두 상세 화면이 같은 모양으로 보이도록 여기 모은다.
 * (컴포넌트만 둔다 — 상태 판정 함수는 utils/incidentStatus)
 *
 * 색은 프로젝트 색을 쓴다 — 글자 #0b1c30, 보조 #424754, 흐림 #727785,
 * 테두리 #c2c6d6, 바탕 #f8f9ff, 강조 #0058be, 강조 바탕 #e5eeff.
 */

/** 드론 표시. 어디서나 같은 모양(색 점 + id) — 지도와 같은 색이다. */
export function DroneChip({ id }) {
  if (!id) return <span className="text-xs text-[#727785]">미기록</span>;
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold text-[#0b1c30] whitespace-nowrap">
      <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: droneColor(id) }} />
      {id}
    </span>
  );
}

/** 기록이 없을 때·불러오는 중일 때. 목록 자리 가운데에 같은 모양으로 뜬다. */
export function EmptyState({ icon, title, hint }) {
  return (
    <div className="h-full min-h-[280px] flex flex-col items-center justify-center gap-2 text-center px-6">
      <span className="material-symbols-outlined text-5xl text-[#c2c6d6]">{icon}</span>
      <p className="text-sm font-semibold text-[#424754]">{title}</p>
      {hint && <p className="text-xs text-[#727785]">{hint}</p>}
    </div>
  );
}

/** 상세 화면 머리 — 뒤로가기 · 제목 · 부가 정보 · 오른쪽 상태. */
export function DetailHeader({ onBack, title, meta, right }) {
  return (
    <div className="flex items-center gap-4 bg-white px-4 py-3 rounded-xl border border-[#c2c6d6]/70 shadow-sm shrink-0">
      <button
        type="button"
        onClick={onBack}
        title="목록으로"
        className="w-9 h-9 shrink-0 flex items-center justify-center rounded-lg border border-[#c2c6d6] text-[#424754] hover:bg-[#e5eeff] hover:text-[#0058be] transition-colors cursor-pointer"
      >
        <span className="material-symbols-outlined text-[20px]">arrow_back</span>
      </button>
      <div className="min-w-0">
        <h3 className="text-base font-bold text-[#0b1c30] flex items-center gap-2">{title}</h3>
        {meta && <p className="text-xs text-[#727785] tabular-nums truncate">{meta}</p>}
      </div>
      {right && <div className="ml-auto flex items-center gap-2 shrink-0">{right}</div>}
    </div>
  );
}

/** 상세 화면 안의 구역 이름 */
export function SectionLabel({ icon, children }) {
  return (
    <h4 className="text-xs font-bold text-[#727785] uppercase tracking-wider mb-2 flex items-center gap-1">
      {icon && <span className="material-symbols-outlined text-[16px]">{icon}</span>}
      {children}
    </h4>
  );
}

/** 사고 조치 상태 — 대기 / 승인 / 송출 완료 */
export function StatusPill({ status }) {
  const s = statusInfo(status);
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-bold whitespace-nowrap ${s.cls}`}>
      <span className="material-symbols-outlined text-[14px] leading-none">{s.icon}</span>
      {s.label}
    </span>
  );
}
