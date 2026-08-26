import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents, Polyline } from 'react-leaflet';
import L from 'leaflet';
import useDroneStore from '../../store/useDroneStore';
import { saveRoute, saveStation, saveWaypoints } from '../../services/api';

// Leaflet 기본 아이콘 경로 문제 해결
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const droneIcon = new L.DivIcon({
  html: `<div style="width: 24px; height: 24px; background: rgba(0, 88, 190, 0.2); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px rgba(0, 88, 190, 0.5);">
          <div style="width: 10px; height: 10px; background: #0058be; border-radius: 50%;"></div>
         </div>`,
  className: '',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

// 오프라인 드론 커스텀 마커 아이콘 (회색)
const offlineDroneIcon = new L.DivIcon({
  html: `<div style="width: 24px; height: 24px; background: rgba(156, 163, 175, 0.2); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px rgba(156, 163, 175, 0.5);">
          <div style="width: 10px; height: 10px; background: #6b7280; border-radius: 50%;"></div>
         </div>`,
  className: '',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

// 커스텀 웨이포인트 마커 아이콘 — 순서를 알아야 편집이 되므로 번호를 박는다
const waypointIcon = (step) => new L.DivIcon({
  html: `<div title="클릭하면 이 지점을 삭제합니다" style="width: 20px; height: 20px; background: #ea4335; border: 2px solid white; border-radius: 50%; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: 700; cursor: pointer;">${step}</div>`,
  className: '',
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

// 커스텀 스테이션 마커 아이콘 (주황색 바탕 집 모양)
const stationIcon = new L.DivIcon({
  html: `<div style="width: 32px; height: 32px; background: #f97316; border: 2px solid white; border-radius: 8px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
          <span class="material-symbols-outlined" style="color: white; font-size: 20px;">home</span>
         </div>`,
  className: '',
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

// 커스텀 임시 스테이션 마커 아이콘 (반투명 점멸)
const tempStationIcon = new L.DivIcon({
  html: `<div style="width: 32px; height: 32px; background: rgba(249, 115, 22, 0.5); border: 2px dashed #f97316; border-radius: 8px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); animation: pulse 2s infinite;">
          <span class="material-symbols-outlined" style="color: #f97316; font-size: 20px;">home</span>
         </div>`,
  className: '',
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

// GPS 이동 컨트롤 컴포넌트 (Map 안에서 map 객체를 얻기 위해 분리)
function GpsControl({ drones, selectedDroneId }) {
  const map = useMap();
  const isCameraTracking = useDroneStore(state => state.isCameraTracking);
  const setIsCameraTracking = useDroneStore(state => state.setIsCameraTracking);

  // 추적 대상: 선택된 드론 → 없으면 순찰 중 → 없으면 첫 번째
  const target = selectedDroneId
    ? drones.find(d => d.id === selectedDroneId)
    : (drones.find(d => d.status === 'PATROLLING') || drones[0]);

  const handleClick = () => {
    if (isCameraTracking) {
      setIsCameraTracking(false);
      return;
    }
    // 켤 때는 즉시 한 번 맞춰준다 (다음 텔레메트리를 기다리지 않게)
    if (target && typeof target.lat === 'number' && typeof target.lng === 'number') {
      map.setView([target.lat, target.lng], map.getZoom(), { animate: true });
    }
    setIsCameraTracking(true);
  };

  const btnStyle = isCameraTracking
    ? "w-12 h-12 flex items-center justify-center bg-blue-600 rounded-full shadow-md border border-blue-700 hover:bg-blue-700 text-white transition-colors shadow-blue-500/50"
    : "w-12 h-12 flex items-center justify-center bg-white rounded-full shadow-md border border-gray-300 hover:bg-gray-50 text-gray-600 transition-colors";

  return (
    <div className="absolute bottom-6 left-6 flex flex-col gap-2 z-[400]">
      <button
        onClick={handleClick}
        className={btnStyle}
        disabled={!target}
        title={isCameraTracking ? "따라가기 끄기" : "드론 따라가기"}
      >
        <span className={`material-symbols-outlined ${isCameraTracking ? 'animate-pulse' : ''}`}>
          {isCameraTracking ? 'location_searching' : 'my_location'}
        </span>
      </button>
    </div>
  );
}

/**
 * 드론 따라가기. 최상위에 둬야 한다 —
 * DroneMap 안에 정의하면 렌더마다 새 컴포넌트로 취급되어 매초(텔레메트리 주기)
 * 언마운트·재마운트되고, Leaflet 이벤트 핸들러가 계속 붙었다 떨어진다.
 */
function CameraTracker() {
  const map = useMap();
  const selectedDroneId = useDroneStore(state => state.selectedDroneId);
  const isCameraTracking = useDroneStore(state => state.isCameraTracking);
  const setIsCameraTracking = useDroneStore(state => state.setIsCameraTracking);
  const drones = useDroneStore(state => state.drones);

  // 우리가 마지막으로 맞춰놓은 지점. 사용자가 민 것인지 판별하는 기준이 된다.
  const lastTargetRef = useRef(null);
  const draggingRef = useRef(false);

  useMapEvents({
    dragstart: () => { draggingRef.current = true; },

    // moveend가 아니라 dragend를 쓴다 — moveend는 우리가 부른 panTo에서도 울린다.
    // dragstart로 즉시 끄면 살짝만 밀어도 풀리므로, 손을 뗀 뒤 벗어난 거리로 판단한다.
    dragend: () => {
      draggingRef.current = false;
      if (!isCameraTracking || !lastTargetRef.current) return;

      const targetPt = map.latLngToContainerPoint(L.latLng(lastTargetRef.current));
      const centerPt = map.latLngToContainerPoint(map.getCenter());
      const size = map.getSize();
      const limit = Math.min(size.x, size.y) / 2;   // 화면 절반 이상 벗어나면 사용자 조작

      if (centerPt.distanceTo(targetPt) > limit) {
        // ⚠️ 진행 중인 panTo 애니메이션을 끊는다.
        //    안 끊으면 추적을 끄는 순간에도 애니메이션이 완주해서
        //    "드론 쪽으로 확 돌아갔다가 꺼지는" 것처럼 보인다.
        map.stop();
        setIsCameraTracking(false);
      }
    },
  });

  useEffect(() => {
    if (!isCameraTracking || !selectedDroneId) return;
    // 사용자가 미는 중에는 끼어들지 않는다. 끼어들면 화면을 서로 잡아당긴다.
    if (draggingRef.current) return;

    const t = drones.find(d => d.id === selectedDroneId);
    if (!t || typeof t.lat !== 'number' || typeof t.lng !== 'number') return;
    lastTargetRef.current = [t.lat, t.lng];   // panTo보다 먼저 갱신해야 dragend가 오판하지 않는다
    map.panTo([t.lat, t.lng], { animate: true, duration: 0.5 });
  }, [isCameraTracking, selectedDroneId, drones, map]);

  return null;
}

// 지도 클릭 이벤트 핸들러 컴포넌트
function MapClickHandler() {
  const isDrawingRoute = useDroneStore(state => state.isDrawingRoute);
  const isSettingStation = useDroneStore(state => state.isSettingStation);
  const addRoutePoint = useDroneStore(state => state.addRoutePoint);
  const setTempStationCoords = useDroneStore(state => state.setTempStationCoords);

  useMapEvents({
    click(e) {
      if (isDrawingRoute) {
        addRoutePoint({ lat: e.latlng.lat, lng: e.latlng.lng });
      } else if (isSettingStation) {
        setTempStationCoords({ lat: e.latlng.lat, lng: e.latlng.lng });
      }
    },
  });
  return null;
}

// 미리보기용 번호 마커. 그리기(빨강)와 구분하려고 파란색을 쓴다.
const previewIcon = (step) => new L.DivIcon({
  html: `<div style="width: 20px; height: 20px; background: #0058be; border: 2px solid white; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: 700; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">${step}</div>`,
  className: '',
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

export default function DroneMap() {
  const drones = useDroneStore((state) => state.drones);
  const selectedDroneId = useDroneStore((state) => state.selectedDroneId);
  const isDrawingRoute = useDroneStore((state) => state.isDrawingRoute);
  const isSettingStation = useDroneStore((state) => state.isSettingStation);
  const drawingTargetDroneId = useDroneStore((state) => state.drawingTargetDroneId);
  const drawingRoute = useDroneStore((state) => state.drawingRoute);
  const routePoints = useDroneStore((state) => state.routePoints);
  const previewRoute = useDroneStore((state) => state.previewRoute);
  const tempStationCoords = useDroneStore((state) => state.tempStationCoords);
  const stopDrawingRoute = useDroneStore((state) => state.stopDrawingRoute);
  const undoRoutePoint = useDroneStore((state) => state.undoRoutePoint);
  const removeRoutePoint = useDroneStore((state) => state.removeRoutePoint);
  const clearRoutePoints = useDroneStore((state) => state.clearRoutePoints);
  const stopSettingStation = useDroneStore((state) => state.stopSettingStation);

  const defaultCenter = [36.6212, 127.2876]; // 홍익대 세종캠퍼스 기준

  const handleSaveRoute = async () => {
    if (routePoints.length < 2) {
      alert("최소 2개 이상의 웨이포인트를 지정해주세요.");
      return;
    }
    try {
      if (drawingRoute) {
        // 저장된 순찰 경로(Route) 편집 — 드론에는 보내지 않고 DB에만 반영한다.
        await saveWaypoints(drawingRoute.routeId, routePoints);
        alert(`'${drawingRoute.routeName}' 경로가 저장되었습니다.`);
      } else {
        await saveRoute(drawingTargetDroneId, routePoints);
        alert("경로가 전송되었습니다. 순찰시작을 누르세요.");
      }
      stopDrawingRoute();
    } catch (e) {
      alert(drawingRoute ? "경로 저장 실패" : "경로 전송 실패");
    }
  };

  const handleSaveStation = async () => {
    if (!tempStationCoords) {
      alert("지도에 클릭하여 스테이션 위치를 지정해주세요.");
      return;
    }
    try {
      await saveStation(drawingTargetDroneId, tempStationCoords.lat, tempStationCoords.lng);
      
      // 스토어에 스테이션 정보 반영 (지도에 주황색 홈 아이콘 표시용 및 복귀 로직용)
      useDroneStore.getState().updateDroneData({
        id: drawingTargetDroneId,
        station: { lat: tempStationCoords.lat, lng: tempStationCoords.lng }
      });
      
      alert("스테이션(기지) 위치가 갱신되었습니다.");
      stopSettingStation();
    } catch (e) {
      alert("스테이션 전송 실패");
    }
  };

  return (
    <div className="absolute inset-0 z-0">
      <MapContainer 
        center={defaultCenter} 
        zoom={16} 
        maxZoom={24}
        style={{ height: '100%', width: '100%', cursor: isDrawingRoute ? 'crosshair' : 'grab' }}
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
          maxNativeZoom={19}
          maxZoom={24}
        />
        <CameraTracker />
        <MapClickHandler />
        
        {/* 드론 마커 & 스테이션 마커 */}
        {drones.map(drone => (
          <React.Fragment key={drone.id}>
            {/* 드론 본체 마커 — 위치를 한 번도 받지 못한 드론(등록만 된 상태)은 그리지 않는다 */}
            {typeof drone.lat === 'number' && typeof drone.lng === 'number' && (
              <Marker position={[drone.lat, drone.lng]} icon={drone.status === 'OFFLINE' ? offlineDroneIcon : droneIcon}>
                <Popup>
                  <div className="text-center font-sans">
                    <p className="font-bold text-sm mb-1">{drone.id}</p>
                    <p className="text-xs text-gray-600">Alt: {drone.altitude}m</p>
                    <p className="text-xs text-gray-600">Bat: {drone.battery}%</p>
                  </div>
                </Popup>
              </Marker>
            )}
            
            {/* 스테이션은 고정 지형지물이고 드론은 움직이는 관제 대상이다.
                겹칠 때 드론이 가려지면 위치를 놓치므로 스테이션을 뒤로 깐다. */}
            {drone.station && drone.station.lat && drone.station.lng && (
              <Marker position={[drone.station.lat, drone.station.lng]} icon={stationIcon} zIndexOffset={-1000}>
                <Popup>
                  <div className="text-center font-sans">
                    <p className="font-bold text-sm text-orange-600 mb-1">{drone.id} Station</p>
                    <p className="text-[10px] text-gray-500">Home Base</p>
                  </div>
                </Popup>
              </Marker>
            )}
          </React.Fragment>
        ))}

        {/* 순찰 시작 팝업의 경로 미리보기.
            ⚠️ 그리기 모드일 때는 그리지 않는다 — 둘 다 보이면 어느 것이 저장될 경로인지 알 수 없다. */}
        {!isDrawingRoute && previewRoute.length > 0 && (
          <>
            {previewRoute.length > 1 && (
              <Polyline positions={previewRoute.map(p => [p.lat, p.lng])} color="#0058be" weight={4} opacity={0.8} />
            )}
            {previewRoute.map((pt, idx) => (
              <Marker key={`pv-${idx}`} position={[pt.lat, pt.lng]} icon={previewIcon(idx + 1)} />
            ))}
          </>
        )}

        {/* 경로 그리기 모드일 때 Polyline과 Waypoint 렌더링 */}
        {routePoints.length > 0 && (
          <Polyline 
            positions={routePoints.map(p => [p.lat, p.lng])} 
            color="#ea4335" 
            weight={3} 
            dashArray="5, 10" 
          />
        )}
        {routePoints.map((pt, idx) => (
          <Marker
            key={idx}
            position={[pt.lat, pt.lng]}
            icon={waypointIcon(idx + 1)}
            /* 마커 클릭은 지도 클릭으로 번지지 않으므로 삭제에 그대로 쓸 수 있다 */
            eventHandlers={{ click: () => removeRoutePoint(idx) }}
          />
        ))}

        {/* 스테이션 설정 모드 임시 마커 렌더링 */}
        {tempStationCoords && (
          <Marker position={[tempStationCoords.lat, tempStationCoords.lng]} icon={tempStationIcon} />
        )}

        {/* GPS UI 오버레이 (Map 객체 제어를 위해 MapContainer 안으로 이동) */}
        <GpsControl drones={drones} selectedDroneId={selectedDroneId} />
      </MapContainer>

      {/* 경로 그리기 오버레이 UI */}
      {isDrawingRoute && (
        <div className="absolute top-6 left-1/2 -translate-x-1/2 z-[500] bg-white px-6 py-4 rounded-full shadow-lg border border-red-200 flex items-center gap-4 animate-in fade-in slide-in-from-top-4 duration-300">
          <div className="flex items-center gap-2">
            <span className="flex h-3 w-3 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
            </span>
            <span className="text-sm font-bold text-gray-800">
              {drawingRoute ? `지도에 클릭하여 '${drawingRoute.routeName}' 경로 편집` : `지도에 클릭하여 ${drawingTargetDroneId}의 순찰 경로 지정`}
            </span>
          </div>
          <div className="h-6 w-px bg-gray-300 mx-2"></div>
          {/* 지점을 되돌릴 수단이 없으면 경로 수정이 불가능하다 (추가만 되고 못 줄임) */}
          <button
            onClick={undoRoutePoint}
            disabled={routePoints.length === 0}
            className="text-sm font-bold text-gray-600 hover:text-gray-900 disabled:opacity-30 disabled:hover:text-gray-600 px-2 flex items-center gap-1"
            title="마지막 지점 취소"
          >
            <span className="material-symbols-outlined text-[18px]">undo</span>
            되돌리기
          </button>
          <button
            onClick={clearRoutePoints}
            disabled={routePoints.length === 0}
            className="text-sm font-bold text-gray-600 hover:text-gray-900 disabled:opacity-30 disabled:hover:text-gray-600 px-2"
            title="지점 전체 삭제"
          >
            전체 지우기
          </button>
          <button
            onClick={stopDrawingRoute}
            className="text-sm font-bold text-gray-500 hover:text-gray-700 px-2"
          >
            취소
          </button>
          <button 
            onClick={handleSaveRoute}
            className="text-sm font-bold bg-red-600 text-white px-4 py-1.5 rounded-full hover:bg-red-700 transition-colors shadow-sm"
          >
            경로 저장 ({routePoints.length}점)
          </button>
        </div>
      )}

      {/* 스테이션 설정 오버레이 UI */}
      {isSettingStation && (
        <div className="absolute top-6 left-1/2 -translate-x-1/2 z-[500] bg-white px-6 py-4 rounded-full shadow-lg border border-orange-200 flex items-center gap-4 animate-in fade-in slide-in-from-top-4 duration-300">
          <div className="flex items-center gap-2">
            <span className="flex h-3 w-3 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-orange-500"></span>
            </span>
            <span className="text-sm font-bold text-gray-800">
              지도에 클릭하여 {drawingTargetDroneId}의 스테이션(기지) 지정
            </span>
          </div>
          <div className="h-6 w-px bg-gray-300 mx-2"></div>
          <button 
            onClick={() => {
              const targetDrone = drones.find(d => d.id === drawingTargetDroneId);
              if (targetDrone && targetDrone.lat && targetDrone.lng) {
                useDroneStore.getState().setTempStationCoords({ lat: targetDrone.lat, lng: targetDrone.lng });
              } else {
                alert("드론의 현재 위치를 알 수 없습니다.");
              }
            }}
            className="text-sm font-bold text-blue-600 hover:text-blue-800 px-2 flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[16px]">my_location</span>
            드론 위치로 지정
          </button>
          <div className="h-6 w-px bg-gray-300 mx-2"></div>
          <button 
            onClick={stopSettingStation}
            className="text-sm font-bold text-gray-500 hover:text-gray-700 px-2"
          >
            취소
          </button>
          <button 
            onClick={handleSaveStation}
            className="text-sm font-bold bg-orange-500 text-white px-4 py-1.5 rounded-full hover:bg-orange-600 transition-colors shadow-sm"
          >
            스테이션 갱신
          </button>
        </div>
      )}
    </div>
  );
}
