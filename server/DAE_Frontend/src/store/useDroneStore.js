import { create } from 'zustand';

// 시스템 알림(순찰·복귀·배터리)은 클라이언트가 텔레메트리 전이를 보고 만든 것이라 서버에 없다.
// 새로고침에서 살아남도록 localStorage에 둔다.
// VLM 경보는 event_logs에 있으므로 여기 저장하지 않고, 접속 시 서버에서 복원한다(App.jsx).
//   → 브라우저별로 다르게 보인다는 한계가 있다.
//     관제사가 여러 PC를 오가야 한다면 서버 저장으로 방향을 바꿔야 한다.
const SYSTEM_ALERT_KEY = 'dae.systemAlerts';

// X로 숨긴 알림 id. 새로고침해도 다시 뜨지 않게 기억한다.
// VLM 경보는 미조치인 한 서버에서 계속 복원되므로, 이 목록이 없으면 X를 눌러도 돌아온다.
// 조치가 끝난 것이 아니라 "지금은 보지 않겠다"는 뜻이므로, 패널에서 되살릴 수 있어야 한다.
const DISMISSED_KEY = 'dae.dismissedAlerts';

const loadDismissed = () => {
  try { return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]')); }
  catch { return new Set(); }
};

const saveDismissed = (set_) => {
  try { localStorage.setItem(DISMISSED_KEY, JSON.stringify([...set_])); } catch { /* 무시 */ }
};

const loadSystemAlerts = () => {
  try {
    const raw = localStorage.getItem(SYSTEM_ALERT_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];   // 손상된 값이 화면을 막지 않도록 조용히 비운다
  }
};

const saveSystemAlerts = (alerts) => {
  try {
    localStorage.setItem(SYSTEM_ALERT_KEY, JSON.stringify(alerts.filter((a) => a.source === 'System')));
  } catch { /* 용량 초과 등은 무시한다. 알림 저장이 실패해도 관제는 계속돼야 한다 */ }
};

const useDroneStore = create((set) => ({
  // 드론 목록은 전적으로 DB(seedRegisteredDrones)와 텔레메트리로만 채운다.
  // 하드코딩된 가짜 드론을 두면 신호가 없어도 실측처럼 표시되므로 두지 않는다.
  drones: [],
  alerts: loadSystemAlerts(),
  // 숨긴 알림 — 개수만 보여주고, 누르면 전부 되살린다
  dismissed: [],
  dismissedIds: loadDismissed(),
  ttsModal: { isOpen: false, alertId: null },
  isAlertPanelOpen: false,
  isRouteManagerOpen: false,
  isDroneStatusOpen: false,
  hasUnsavedChanges: false,
  setHasUnsavedChanges: (val) => set({ hasUnsavedChanges: val }),
  isDrawingRoute: false,
  drawingTargetDroneId: null,
  // 경로 그리기의 저장 대상. null이면 드론에 직접 저장, 값이 있으면 저장된 순찰 경로(Route)에 저장한다.
  drawingRoute: null,
  routePoints: [],
  // 순찰 시작 팝업에서 고른 경로를 지도에 미리 보여주기 위한 것.
  // 그리기(routePoints)와는 별개다 — 저장 대상이 아니라 보기 전용이다.
  previewRoute: [],
  updateDroneData: (newDroneData) => {
    // ⚠️ 알림 생성을 set()의 updater 안에서 하면 안 된다.
    //    updater는 순수해야 하고, 상황에 따라 두 번 호출될 수 있어 알림이 복제된다.
    //    (실제로 "스테이션 복귀 완료"가 두 장씩 쌓였다)
    //    판정과 부수효과는 여기서 한 번만 수행하고, set은 상태 갱신만 한다.
    const store = useDroneStore.getState();
    const existingDrone = store.drones.find((d) => d.id === newDroneData.id);

    // 임무 종료 — 순찰 완주·스테이션 복귀 모두 착륙하지 않고 호버링하므로
    // IDLE 전이로는 알 수 없다. currentAction이 바뀌는 "순간"만 잡는다.
    const DONE = { PATROL_COMPLETE: 'patrol', RETURN_COMPLETE: 'return' };
    const doneKind = existingDrone &&
      existingDrone.currentAction !== newDroneData.currentAction &&
      DONE[newDroneData.currentAction];

    // 같은 드론의 같은 종류 완료 알림이 아직 미조치로 남아 있으면 더 쌓지 않는다.
    const already = doneKind && store.alerts.some(
      (a) => a.droneId === newDroneData.id && a.status === 'PENDING' &&
             a.actionType === (doneKind === 'return' ? 'RETURN_DONE' : 'PATROL_DONE'));

    if (doneKind && !already) {
      const isReturn = doneKind === 'return';
      const alertId = `${newDroneData.id}-${doneKind}-${Date.now()}`;
      store.addAlert({
        id: alertId,
        type: 'Info',
        time: new Date().toLocaleTimeString('ko-KR', { hour12: false }),
        // 외부 스톡 사진 대신 아이콘을 쓴다. 이 드론의 사진도 아니었고,
        // 인터넷이 끊기면 깨진 이미지가 뜨며, 알림마다 외부 요청이 나갔다.
        icon: isReturn ? 'drone' : 'task_alt',
        tone: isReturn ? 'blue' : 'green',
        title: isReturn ? '스테이션 복귀 완료' : '순찰 임무 완료',
        desc: isReturn
          ? `${newDroneData.id}가 스테이션 상공에서 대기 중입니다.`
          : `${newDroneData.id}가 순찰을 완료하고 대기 중입니다.`,
        source: 'System',
        droneId: newDroneData.id,
        actionType: isReturn ? 'RETURN_DONE' : 'PATROL_DONE',
      });
      store.setAlertPanelOpen(true);
      // 조치(안전 착륙 등) 후 이 알림을 회색 처리하려면 어느 알림인지 알아야 한다.
      store.openMissionDoneModal(newDroneData.id, doneKind, alertId);
    }

    // 배터리 자율 복귀 개시 — 관제사가 지시하지 않은 비행이다.
    // 사유를 알리지 않으면 관제사는 왜 복귀가 시작됐는지 알 수 없다(통신 스펙 §페일세이프).
    // 완료 알림과 마찬가지로 currentAction이 "바뀌는 순간"만 잡는다 — 매 틱 쌓이면 안 된다.
    const batteryRtlStarted = existingDrone &&
      existingDrone.currentAction !== 'BATTERY_RTL' &&
      newDroneData.currentAction === 'BATTERY_RTL';

    if (batteryRtlStarted) {
      store.addAlert({
        id: `${newDroneData.id}-battery-rtl-${Date.now()}`,
        type: 'Critical',
        time: new Date().toLocaleTimeString('ko-KR', { hour12: false }),
        icon: 'battery_alert', tone: 'red',
        title: '배터리 자율 복귀',
        desc: `${newDroneData.id}가 배터리 부족으로 스스로 복귀합니다. 도착 후 착륙합니다.`,
        source: 'System', droneId: newDroneData.id, actionType: 'BATTERY_RTL',
      });
      store.setAlertPanelOpen(true);
    }

    // 드론은 40%에서 스스로 복귀한다(드론팀 정책). 경고가 같은 지점이면
    // 관제사가 경고를 보는 순간 이미 복귀가 시작돼 판단할 시간이 없다.
    // 60%에서 알려 40%까지의 여유를 준다.
    if (existingDrone && existingDrone.battery > 60 && newDroneData.battery <= 60) {
      store.addAlert({
        id: `${newDroneData.id}-battery-${Date.now()}`,
        type: 'Warning',
        time: new Date().toLocaleTimeString('ko-KR', { hour12: false }),
        icon: 'battery_alert', tone: 'amber',
        title: '배터리 부족 경고', desc: `${newDroneData.id} 배터리 60% 이하. 40%에서 자동 복귀합니다.`,
        source: 'System', droneId: newDroneData.id, actionType: 'BATTERY',
      });
      store.setAlertPanelOpen(true);
    }

    set((state) => {
      const cur = state.drones.find((d) => d.id === newDroneData.id);
      if (cur) {
        return { drones: state.drones.map((d) => d.id === newDroneData.id
          ? { ...d, ...newDroneData, lastSeen: Date.now(),
              station: newDroneData.station || (newDroneData.stationLat
                ? { lat: newDroneData.stationLat, lng: newDroneData.stationLng } : d.station) }
          : d) };
      }
      return { drones: [...state.drones, { ...newDroneData, lastSeen: Date.now(),
        station: newDroneData.station || (newDroneData.stationLat
          ? { lat: newDroneData.stationLat, lng: newDroneData.stationLng } : null) }] };
    });
  },

  // DB에 등록된 드론을 목록에 미리 채운다. 전원이 꺼져 있어도 OFFLINE으로 표시되며,
  // 텔레메트리가 도착하면 updateDroneData가 같은 id를 찾아 상태·위치를 갱신한다.
  seedRegisteredDrones: (dbDrones) => set((state) => {
    const newOnes = dbDrones
      .filter((d) => d.droneId && !state.drones.some((x) => x.id === d.droneId))
      .map((d) => ({
        id: d.droneId,
        name: d.droneName,
        status: 'OFFLINE',
        battery: 0,
        altitude: 0,
        lat: null,   // 신호를 받기 전에는 위치를 모른다 (지도 마커도 그리지 않음)
        lng: null,
        // 스테이션은 신호가 없어도 알아야 지도에 홈 마커를 그린다.
        // 텔레메트리가 오면 updateDroneData가 덮어쓴다(드론이 보고하는 값이 우선).
        station: (d.stationLat != null && d.stationLng != null)
          ? { lat: d.stationLat, lng: d.stationLng }
          : null,
      }));
    return newOnes.length ? { drones: [...state.drones, ...newOnes] } : state;
  }),

  // 일정 시간 동안 텔레메트리가 끊긴 드론을 OFFLINE으로 되돌린다.
  // lastSeen이 없는 항목(DB 시드 직후, 아직 한 번도 신호를 받지 못한 드론)은 건드리지 않는다.
  markStaleDronesOffline: (timeoutMs = 10000) => set((state) => {
    const now = Date.now();
    let changed = false;
    const drones = state.drones.map((d) => {
      if (d.lastSeen && d.status !== 'OFFLINE' && now - d.lastSeen > timeoutMs) {
        changed = true;
        return { ...d, status: 'OFFLINE' };
      }
      return d;
    });
    return changed ? { drones } : state;
  }),

  addAlert: (alert) => set((state) => {
    // 같은 알림이 두 번 들어오지 않게 한다(서버 복원 + 실시간 수신이 겹칠 수 있다).
    if (state.alerts.some(a => a.id === alert.id)) return state;
    // X로 숨긴 것은 서버에서 다시 복원돼도 띄우지 않는다.
    if (state.dismissedIds.has(alert.id)) {
      return state.dismissed.some(a => a.id === alert.id)
        ? state : { dismissed: [alert, ...state.dismissed] };
    }
    const alerts = [{ ...alert, status: 'PENDING' }, ...state.alerts];
    saveSystemAlerts(alerts);
    return { alerts };
  }),
  clearAlerts: () => { saveSystemAlerts([]); return set({ alerts: [] }); },
  /**
   * 알림 숨기기. 지우는 것이 아니라 접어두는 것이다.
   * 조치가 필요한 건(VLM 경보)은 HISTORY에도 남아 있고, 아래 restoreDismissed로 되살릴 수도 있다.
   */
  dismissAlert: (alertId) => set((state) => {
    const target = state.alerts.find(a => a.id === alertId);
    const alerts = state.alerts.filter(a => a.id !== alertId);
    const dismissedIds = new Set(state.dismissedIds).add(alertId);
    saveSystemAlerts(alerts);
    saveDismissed(dismissedIds);
    return { alerts, dismissedIds, dismissed: target ? [target, ...state.dismissed] : state.dismissed };
  }),
  /** 숨긴 알림을 전부 되살린다. 조치를 다시 하려면 이 통로가 필요하다. */
  restoreDismissed: () => set((state) => {
    const dismissedIds = new Set();
    saveDismissed(dismissedIds);
    const alerts = [...state.dismissed, ...state.alerts];
    saveSystemAlerts(alerts);
    return { alerts, dismissed: [], dismissedIds };
  }),
  resolveAlert: (alertId) => set((state) => {
    const alerts = state.alerts.map(a => a.id === alertId ? { ...a, status: 'RESOLVED' } : a);
    saveSystemAlerts(alerts);
    return { alerts };
  }),
  openTTSModal: (alertId) => set({ ttsModal: { isOpen: true, alertId } }),
  closeTTSModal: () => set({ ttsModal: { isOpen: false, alertId: null } }),
  // 임무를 마치고 공중 대기 중인 드론에 다음 지시를 묻는 팝업.
  // 드론이 스스로 내려앉지 않으므로, 관제사가 착륙을 지시할 통로가 필요하다.
  // 실시간 영상. 한 번에 한 대만 본다 — 서버도 한 대만 중계한다.
  liveStreamModal: { isOpen: false, droneId: null },
  openLiveStream: (droneId) => set({ liveStreamModal: { isOpen: true, droneId } }),
  closeLiveStream: () => set({ liveStreamModal: { isOpen: false, droneId: null } }),

  missionDoneModal: { isOpen: false, droneId: null, kind: null, alertId: null },
  openMissionDoneModal: (droneId, kind, alertId) => set({ missionDoneModal: { isOpen: true, droneId, kind, alertId } }),
  closeMissionDoneModal: () => set({ missionDoneModal: { isOpen: false, droneId: null, kind: null, alertId: null } }),

  cancelModal: { isOpen: false, droneId: null },
  openCancelModal: (droneId) => set({ cancelModal: { isOpen: true, droneId } }),
  closeCancelModal: () => set({ cancelModal: { isOpen: false, droneId: null } }),
  toggleAlertPanel: () => set((state) => ({ isAlertPanelOpen: !state.isAlertPanelOpen })),
  setAlertPanelOpen: (isOpen) => set({ isAlertPanelOpen: isOpen }),
  setDroneManagementOpen: (isOpen) => set({ isDroneManagementOpen: isOpen }),
  setDroneSettings: (settings) => set({ droneSettings: settings }),
  setRouteManagerOpen: (isOpen) => set({ isRouteManagerOpen: isOpen }),
  setDroneStatusOpen: (isOpen) => set({ isDroneStatusOpen: isOpen }),
  openStartPatrolModal: (droneId) => set({ isStartPatrolModalOpen: true, startPatrolTargetId: droneId }),
  closeStartPatrolModal: () => set({ isStartPatrolModalOpen: false, startPatrolTargetId: null }),
  
  isRegisterModalOpen: false,
  openRegisterModal: () => set({ isRegisterModalOpen: true }),
  closeRegisterModal: () => set({ isRegisterModalOpen: false }),

  // ⚠️ 아래 둘은 이름이 달라야 한다. 객체 리터럴에서 키가 겹치면 뒤엣것이 앞엣것을 조용히 덮는다.
  //    (2026-08-17: Way→Route 일괄 치환으로 둘 다 startDrawingRoute가 되어
  //     드론 경로 지정이 저장경로 편집으로 흘러 들어가 routeId가 undefined가 됐다)

  // 드론에 즉시 보낼 경로를 그린다. 저장하지 않고 STOMP로 전송한다.
  startDrawingDroneRoute: (droneId) => set({ isDrawingRoute: true, drawingTargetDroneId: droneId, drawingRoute: null, routePoints: [] }),
  // 저장된 순찰 경로(PatrolRoute)를 편집한다. 기존 지점이 있으면 이어서 찍도록 미리 채워 준다.
  startEditingRoute: (route, points = []) => set({ isDrawingRoute: true, drawingTargetDroneId: null, drawingRoute: route, routePoints: points }),
  stopDrawingRoute: () => set({ isDrawingRoute: false, drawingTargetDroneId: null, drawingRoute: null, routePoints: [] }),
  addRoutePoint: (point) => set((state) => ({ routePoints: [...state.routePoints, point] })),
  undoRoutePoint: () => set((state) => ({ routePoints: state.routePoints.slice(0, -1) })),
  removeRoutePoint: (index) => set((state) => ({ routePoints: state.routePoints.filter((_, i) => i !== index) })),
  clearRoutePoints: () => set({ routePoints: [] }),
  setPreviewRoute: (points) => set({ previewRoute: points }),
  clearPreviewRoute: () => set({ previewRoute: [] }),
  startSettingStation: (droneId) => set({ isSettingStation: true, drawingTargetDroneId: droneId, tempStationCoords: null, isDrawingRoute: false }),
  setTempStationCoords: (coords) => set({ tempStationCoords: coords }),
  stopSettingStation: () => set({ isSettingStation: false, drawingTargetDroneId: null, tempStationCoords: null }),
  selectedDroneId: null,
  isCameraTracking: false,
  setSelectedDroneId: (id) => set({ selectedDroneId: id, isCameraTracking: !!id }),
  setIsCameraTracking: (val) => set({ isCameraTracking: val }),
}));
export default useDroneStore;
