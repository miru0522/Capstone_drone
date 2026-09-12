/**
 * 사고 조치 상태·분류. History 표와 상세가 같이 쓴다.
 */

/**
 * 조치가 끝난 사고인가.
 * 서버는 새 사고에 PENDING 을 넣는다 — "값이 있으면 처리됨"으로 보면 대기 중인 건이
 * 처리된 것처럼 보이고 승인 버튼이 사라진다(2026-09-11 확인: 289건 중 285건이 PENDING).
 */
export const isHandled = (status) => status === 'APPROVED' || status === 'BROADCAST_COMPLETED';

const INCIDENT_STATUS = {
  BROADCAST_COMPLETED: { label: '송출 완료', icon: 'campaign', cls: 'bg-green-50 text-green-700 border-green-200' },
  APPROVED: { label: '승인', icon: 'check_circle', cls: 'bg-[#e5eeff] text-[#0058be] border-[#c9d8f5]' },
};
const PENDING_STATUS = { label: '대기', icon: 'schedule', cls: 'bg-amber-50 text-amber-700 border-amber-200' };

/** 상태별 이름·아이콘·색. 모르는 값은 대기로 본다. */
export const statusInfo = (status) => INCIDENT_STATUS[status] ?? PENDING_STATUS;
export const statusLabel = (status) => statusInfo(status).label;

/**
 * 사고 분류 색. 표의 왼쪽 띠·배지·상세가 같이 쓴다.
 * 정상 판정은 경고색으로 보이면 안 된다. 모르는 값은 주의(노랑)로 둔다.
 */
export const classTone = (result) => {
  if (result === 'ASSAULT' || result === 'CRITICAL') return { badge: 'bg-red-50 text-red-700 border-red-200', stripe: 'bg-red-500' };
  if (result === 'FIGHT') return { badge: 'bg-orange-50 text-orange-700 border-orange-200', stripe: 'bg-orange-500' };
  if (result === '정상' || result === 'NORMAL' || result === 'INFO') return { badge: 'bg-slate-50 text-slate-600 border-slate-200', stripe: 'bg-slate-300' };
  return { badge: 'bg-amber-50 text-amber-700 border-amber-200', stripe: 'bg-amber-400' };
};
