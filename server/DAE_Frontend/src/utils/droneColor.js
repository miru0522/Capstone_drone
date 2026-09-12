/**
 * 드론별 색. 지도(마커·스테이션)와 기록 화면이 같은 색을 쓴다.
 *
 * ID로 색을 정한다 — 등록 순서가 바뀌어도 같은 드론은 항상 같은 색이어야 한다.
 */
const DRONE_COLORS = ['#0058be', '#16a34a', '#9333ea', '#ea580c', '#0891b2', '#be123c'];

export const droneColor = (droneId) => {
  let h = 0;
  for (let i = 0; i < String(droneId).length; i++) h = (h * 31 + String(droneId).charCodeAt(i)) | 0;
  return DRONE_COLORS[Math.abs(h) % DRONE_COLORS.length];
};
