/**
 * 드론 상태(status) 표기 규칙.
 *
 * 드론이 보고하는 값을 그대로 키로 쓴다 (통신 스펙 §1).
 * 배지를 그리는 곳이 여러 군데(사이드바 카드, 상태 모달)라 여기 한 곳에서 관리한다.
 */
export const STATUS_STYLE = {
  PATROLLING: { cls: 'bg-green-100 text-green-700 border-green-200',   label: 'PATROLLING' },
  PAUSED:     { cls: 'bg-yellow-100 text-yellow-700 border-yellow-200', label: 'PAUSED' },
  RETURNING:  { cls: 'bg-orange-100 text-orange-700 border-orange-200', label: 'RETURNING' },
  LANDING:    { cls: 'bg-indigo-100 text-indigo-700 border-indigo-200', label: 'LANDING' },
  IDLE:       { cls: 'bg-gray-100 text-gray-700 border-gray-200',       label: 'IDLE' },
  OFFLINE:    { cls: 'bg-gray-100 text-gray-400 border-gray-200',       label: 'OFFLINE' },
};

/**
 * 모르는 값이 와도 화면이 깨지지 않도록 회색으로 떨어뜨린다.
 *
 * currentAction은 선택 인자다 — 넘기지 않으면 예전과 똑같이 동작한다.
 * 배터리 자율 복귀는 관제사가 지시한 복귀와 구분해야 한다. 같은 RETURNING이지만
 * 이유가 다르고, 관제사가 개입할 수 있는 조작도 다르다(DroneStatus의 버튼 참조).
 */
export const statusStyle = (status, currentAction) => {
  if (status === 'RETURNING' && currentAction === 'BATTERY_RTL') {
    return { cls: 'bg-red-100 text-red-700 border-red-300', label: 'RETURNING: LOW BATTERY' };
  }
  return STATUS_STYLE[status] ?? { cls: 'bg-gray-100 text-gray-700 border-gray-200', label: status || '-' };
};

/**
 * 배터리 부족으로 드론이 스스로 복귀하는 중인가.
 * 관제사가 지시한 복귀(currentAction: RETURN_TO_STATION 등)와 구분한다.
 * 판별을 여기 한 곳에만 두어 배지·버튼·경보가 어긋나지 않게 한다.
 */
export const isBatteryRtl = (drone) =>
  drone?.status === 'RETURNING' && drone?.currentAction === 'BATTERY_RTL';

/** 공중에 떠 있는 상태인가 (종료·비상 제어를 노출할지 판단용) */
export const isAirborne = (status) =>
  ['PATROLLING', 'PAUSED', 'RETURNING', 'LANDING'].includes(status);

/** 상태 전환 시 관제사에게 알릴 문구. null이면 알리지 않는다. */
export const STATUS_TOAST = {
  PATROLLING: '순찰을 시작합니다.',
  PAUSED:     '순찰을 중지하고 제자리 대기합니다.',
  RETURNING:  '스테이션으로 복귀합니다.',
  LANDING:    '착륙을 시작합니다.',
  IDLE:       '착륙 및 대기 상태로 전환되었습니다.',
};

/**
 * 배터리 자율 복귀 전용 문구.
 * STATUS_TOAST.RETURNING('스테이션으로 복귀합니다')을 그대로 쓰면 관제사가 자기가 누른
 * 복귀와 구분하지 못한다 — 오히려 "내가 눌렀나 보다"로 읽혀 경고 효과가 사라진다.
 */
export const BATTERY_RTL_TOAST = '배터리 부족으로 스스로 복귀합니다.';
