import React, { useState, useEffect } from 'react';
import useDroneStore from '../../store/useDroneStore';
import { saveRoute, startPatrol, getRoutes, getWaypoints, getDroneRoute } from '../../services/api';
import toast from 'react-hot-toast';

// 프리셋 목록은 "Patrol Routes" 탭에서 관리하는 저장된 경로(Route)를 그대로 쓴다.
// ⚠️ 백엔드 POST /drone/{id}/route 는 List<Map<String,Double>> 를 받는다.
//    즉 [{lat, lng}, ...] 형태여야 하며, [lat, lng] 배열로 보내면 역직렬화 실패로 500이 난다.
//    DroneMap(routePoints)·MissionDoneModal 도 모두 {lat, lng} 형태를 쓴다.
const KEEP = 'keep';

export default function StartPatrolModal() {
  const { isStartPatrolModalOpen, startPatrolTargetId, closeStartPatrolModal } = useDroneStore((state) => state);
  const targetDrone = useDroneStore((state) => state.drones.find(d => d.id === state.startPatrolTargetId));
  const [selectedPresetId, setSelectedPresetId] = useState(KEEP);
  const [routes, setRoutes] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const setPreviewRoute = useDroneStore((state) => state.setPreviewRoute);
  const clearPreviewRoute = useDroneStore((state) => state.clearPreviewRoute);
  // 미리보기로 이미 받아둔 지점. 시작할 때 재조회하지 않으려고 들고 있는다.
  const [previewPoints, setPreviewPoints] = useState([]);

  useEffect(() => {
    if (!isStartPatrolModalOpen) {
      // 취소·시작·바깥클릭 어느 경로로 닫혀도 지도에 경로가 남으면 안 된다
      clearPreviewRoute();
      setPreviewPoints([]);
      return;
    }
    setSelectedPresetId(KEEP);
    getRoutes()
      .then((list) => setRoutes(Array.isArray(list) ? list : []))
      .catch(() => setRoutes([]));   // 경로가 없어도 "지정 순찰 경로"로는 시작할 수 있다
  }, [isStartPatrolModalOpen, clearPreviewRoute]);

  // 선택이 바뀌면 그 경로를 지도에 띄운다.
  useEffect(() => {
    if (!isStartPatrolModalOpen) return;
    let alive = true;

    // KEEP은 드론이 들고 있는 경로다. 서버가 마지막으로 지시한 것을 가져와 그린다.
    // 단, 드론이 hasRoute=false를 보내면 실제로는 비어 있으므로 그리지 않는다.
    if (selectedPresetId === KEEP) {
      if (targetDrone?.hasRoute === false) {
        clearPreviewRoute();
        setPreviewPoints([]);
        return;
      }
      getDroneRoute(startPatrolTargetId)
        .then((pts) => {
          if (!alive) return;
          // 드론 계약은 lon, 지도(Leaflet)는 lng를 쓴다. 예전에 저장된 기록에는
          // lng로 들어간 것도 있으므로 둘 다 받아 흡수한다.
          const points = (Array.isArray(pts) ? pts : [])
            .map(p => ({ lat: p.lat, lng: p.lon ?? p.lng }))
            .filter(p => p.lat != null && p.lng != null);
          setPreviewPoints(points);
          setPreviewRoute(points);
        })
        .catch(() => {
          if (!alive) return;
          setPreviewPoints([]);
          clearPreviewRoute();
        });
      return () => { alive = false; };
    }

    getWaypoints(Number(selectedPresetId))
      .then((pts) => {
        if (!alive) return;
        const points = (Array.isArray(pts) ? pts : []).map(p => ({ lat: p.latitude, lng: p.longitude }));
        setPreviewPoints(points);
        setPreviewRoute(points);
      })
      .catch(() => {
        if (!alive) return;
        setPreviewPoints([]);
        clearPreviewRoute();
      });
    return () => { alive = false; };   // 빠르게 바꿀 때 이전 응답이 나중에 덮어쓰는 것 방지
  }, [selectedPresetId, isStartPatrolModalOpen, startPatrolTargetId, targetDrone?.hasRoute, setPreviewRoute, clearPreviewRoute]);

  if (!isStartPatrolModalOpen) return null;

  // "지정 순찰 경로"를 골랐는데 드론에 경로가 없으면 이륙만 하고 할 일이 없다.
  // 드론이 hasRoute를 안 보내는 구버전이면 판단하지 않는다(undefined → 막지 않음).
  const keepingRoute = selectedPresetId === KEEP;
  const noRouteToKeep = keepingRoute && targetDrone?.hasRoute === false;

  // 경로를 지정하러 지도로 보낸다
  const goDrawRoute = () => {
    closeStartPatrolModal();
    useDroneStore.getState().startDrawingDroneRoute(startPatrolTargetId);
    toast('경로를 지정하고 경로 저장을 누르세요.', { icon: 'route' });
  };

  const handleStart = async () => {
    if (!startPatrolTargetId) return;

    if (noRouteToKeep) {
      toast.error('지정된 경로가 없습니다. 경로를 먼저 지정해 주세요.');
      return;
    }

    setIsLoading(true);
    try {
      // 1. 경로 전송 (ROUTE_UPDATE) — 저장된 경로를 골랐다면 지점을 받아 드론에 내려보낸다
      if (!keepingRoute) {
        // 미리보기에서 이미 받아둔 지점을 그대로 쓴다 (조회 2회 방지)
        const waypoints = previewPoints;
        if (waypoints.length < 2) {
          toast.error('선택한 경로에 지점이 부족합니다. Patrol Routes에서 지점을 지정해 주세요.');
          setIsLoading(false);
          return;
        }
        await saveRoute(startPatrolTargetId, waypoints);
        toast.success(`[${startPatrolTargetId}] 경로 업데이트 완료`);
      }

      // 2. 순찰 시작 (START_PATROL)
      await startPatrol(startPatrolTargetId);
      toast.success(`[${startPatrolTargetId}] 순찰 시작 명령이 전송되었습니다.`);

      closeStartPatrolModal();
    } catch {
      toast.error('순찰 시작 명령 전송 실패');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    /* 몰드지를 두지 않는다 — 뒤 지도에 선택한 경로를 그려 보여줘야 하기 때문이다.
       pointer-events-none으로 지도 조작(패닝·줌)을 막지 않고, 패널만 이벤트를 받는다. */
    <div className="absolute inset-0 z-50 flex items-center justify-end p-6 pointer-events-none animate-in fade-in duration-200">
      <div className="pointer-events-auto bg-white rounded-2xl shadow-2xl border border-[#c2c6d6] w-[380px] flex flex-col overflow-hidden animate-in slide-in-from-right-4 duration-200">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-3 bg-[#f8f9ff]">
          <span className="material-symbols-outlined text-blue-600">drone</span>
          <h2 className="text-lg font-bold text-gray-800">순찰 시작 설정</h2>
          {/* 이 모달은 배경이 없어(지도를 보여줘야 하므로) 바깥 클릭으로 닫을 수 없다.
              닫을 방법이 X 하나뿐이므로 반드시 있어야 한다. */}
          <button
            type="button"
            onClick={closeStartPatrolModal}
            aria-label="닫기"
            className="ml-auto text-gray-400 hover:text-gray-600 transition-colors cursor-pointer leading-none"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        
        <div className="p-6">
          <p className="text-sm text-gray-600 mb-4">
            <span className="font-bold text-blue-600">{startPatrolTargetId}</span> 드론의 순찰을 시작합니다.
            시작하기 전에 적용할 <strong>경로 프리셋</strong>을 선택하세요.
          </p>
          
          <label className="block text-xs font-bold text-gray-500 mb-2 uppercase">Route Preset</label>
          <select 
            className="w-full p-3 border border-gray-300 rounded-lg bg-gray-50 text-sm font-medium focus:ring-2 focus:ring-blue-500 focus:outline-none"
            value={selectedPresetId}
            onChange={(e) => setSelectedPresetId(e.target.value)}
          >
            <option value={KEEP}>지정 순찰 경로</option>
            {routes.map(w => (
              <option key={w.routeId} value={w.routeId}>{w.routeName}</option>
            ))}
          </select>
          {routes.length === 0 && (
            <p className="mt-2 text-xs text-gray-500">
              저장된 순찰 경로가 없습니다. 왼쪽 <strong>Patrol Routes</strong>에서 만들 수 있습니다.
            </p>
          )}
          {/* KEEP은 드론이 들고 있는 경로라 서버가 내용을 모른다 → 지도에 그릴 수 없다 */}
          <p className="mt-2 text-xs text-gray-500 flex items-start gap-1">
            <span className="material-symbols-outlined text-[14px] mt-px">info</span>
            {keepingRoute && previewPoints.length === 0
              ? '드론에 지정된 경로가 없습니다.'
              : `지도에 ${previewPoints.length}개 지점이 표시됩니다.`}
          </p>
        </div>

        {/* "지정 순찰 경로"인데 드론에 경로가 없으면 이륙만 하고 할 일이 없다.
            막기만 하지 말고 경로를 지정하러 갈 수 있게 한다. */}
        {noRouteToKeep && (
          <div className="mx-4 mb-1 p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-2">
            <span className="material-symbols-outlined text-amber-600 text-[18px] shrink-0">warning</span>
            <div className="text-xs text-amber-800">
              <p className="font-bold mb-0.5">지정된 경로가 없습니다.</p>
              <p>경로를 먼저 지정하거나, 위에서 프리셋 경로를 선택해 주세요.</p>
            </div>
          </div>
        )}

        <div className="p-4 bg-gray-50 border-t border-gray-100 flex justify-end gap-2">
          <button
            onClick={closeStartPatrolModal}
            className="px-4 py-2 text-sm font-bold text-gray-600 bg-white border border-gray-300 rounded-lg shadow-sm hover:bg-gray-50"
            disabled={isLoading}
          >
            취소
          </button>
          {noRouteToKeep ? (
            <button
              onClick={goDrawRoute}
              className="px-4 py-2 text-sm font-bold text-white bg-amber-600 border border-amber-700 rounded-lg shadow-sm hover:bg-amber-700 flex items-center gap-2"
              disabled={isLoading}
            >
              <span className="material-symbols-outlined text-[18px]">route</span>
              경로 지정하기
            </button>
          ) : (
            <button
              onClick={handleStart}
              className="px-4 py-2 text-sm font-bold text-white bg-blue-600 border border-blue-700 rounded-lg shadow-sm hover:bg-blue-700 flex items-center gap-2"
              disabled={isLoading}
            >
              {isLoading ? (
                <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
              ) : (
                <span className="material-symbols-outlined text-[18px]">play_arrow</span>
              )}
              비행 시작
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
