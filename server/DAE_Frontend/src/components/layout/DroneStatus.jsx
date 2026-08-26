import React, { useState, useEffect } from 'react';
import useDroneStore from '../../store/useDroneStore';
import useUserStore from '../../store/useUserStore';
import { pausePatrol, cancelPatrol, landPatrol, returnToBase, saveStation, resumePatrol } from '../../services/api';
import api from '../../services/api';
import ControlButton from '../common/ControlButton';
import { statusStyle, isAirborne, isBatteryRtl } from '../../utils/droneStatus';
import toast from 'react-hot-toast';

export default function DroneStatus() {
  const drones = useDroneStore((state) => state.drones);
  const selectedDroneId = useDroneStore((state) => state.selectedDroneId);
  const setSelectedDroneId = useDroneStore((state) => state.setSelectedDroneId);
  // 드론은 팀 공용 자산이다. 목록은 전원, 조작은 ADMIN·OPERATOR, 등록은 ADMIN만.
  const role = useUserStore((state) => state.userInfo?.role);
  // VIEWER는 조회 전용이다. 백엔드가 403으로 막지만, 누를 수 있는 버튼을 보여줄 이유가 없다.
  const canOperate = role === 'ADMIN' || role === 'OPERATOR';
  const openCancelModal = useDroneStore((state) => state.openCancelModal);
  const openLiveStream = useDroneStore((state) => state.openLiveStream);
  const openStartPatrolModal = useDroneStore((state) => state.openStartPatrolModal);
  const droneSettings = useDroneStore((state) => state.droneSettings);

  const [expandedDrone, setExpandedDrone] = useState(null);
  const [registeredDrones, setRegisteredDrones] = useState([]);
  const [isRegisteredExpanded, setIsRegisteredExpanded] = useState(false);

  useEffect(() => {
    const fetchRegistered = async () => {
      try {
        const res = await api.get('/drones');
        setRegisteredDrones(res.data);
      } catch (error) {
        console.error("Failed to fetch registered drones:", error);
      }
    };
    fetchRegistered();
  }, []);

  // 스테이션이 없으면 현재 위치를 임시 스테이션으로 잡고 순찰 시작 모달을 띄운다.
  // (복귀 목표가 없으면 RETURN_TO_STATION이 갈 곳을 모른다)
  const handleStartPatrol = async (drone) => {
    const hasStation = drone.station && (drone.station.lat || drone.station.lat === 0);
    if (!hasStation) {
      if (typeof drone.lat !== 'number' || typeof drone.lng !== 'number') {
        toast.error("지정된 스테이션이 없으며 드론 위치도 확인할 수 없습니다.");
        return;
      }
      toast.success("현재 위치를 임시 스테이션으로 지정합니다.");
      try {
        // saveStation(droneId, lat, lng) — 좌표는 객체가 아니라 개별 인자로 넘긴다.
        await saveStation(drone.id, drone.lat, drone.lng);
        useDroneStore.getState().updateDroneData({
          id: drone.id, station: { lat: drone.lat, lng: drone.lng },
        });
      } catch {
        toast.error("임시 스테이션 지정에 실패했습니다.");
        return;
      }
    }
    openStartPatrolModal(drone.id);
  };

  const safeSettings = Array.isArray(droneSettings) ? droneSettings : [];
  const displayDrones = [...drones].filter(d => {
    const s = safeSettings.find(set => set.droneId === d.id);
    return s ? s.visible : true;
  }).sort((a, b) => {
    const sa = safeSettings.find(set => set.droneId === a.id);
    const sb = safeSettings.find(set => set.droneId === b.id);
    const oa = sa ? sa.sortOrder : 999;
    const ob = sb ? sb.sortOrder : 999;
    return oa - ob;
  });

  return (
    <div className="mt-4 pt-6 border-t border-[#c2c6d6] flex-1 overflow-y-auto [scrollbar-gutter:stable] space-y-4">
      <div className="px-4 flex justify-between items-center">
        <h3 className="text-xs font-medium text-[#727785] uppercase tracking-widest">Units</h3>
        {/* 사이드탭 표시 여부·순서는 계정별 개인 설정(user_drone_settings)이다.
            드론을 등록·삭제하는 기능이 아니므로 VIEWER를 포함해 전원에게 연다. */}
        <button
          onClick={() => useDroneStore.getState().setDroneManagementOpen(true)}
          className="flex items-center gap-1 text-xs font-bold text-[#0058be] bg-[#e5eeff] px-2 py-1 rounded-md hover:bg-[#d0e0ff] transition-colors"
          title="사이드탭에 보일 드론과 순서를 정합니다"
        >
          <span className="material-symbols-outlined text-[14px]">tune</span>
          구성
        </button>
      </div>
      <div className="space-y-2 px-1">
        {displayDrones.map((drone) => (
          <div 
            key={drone.id} 
            onClick={() => setSelectedDroneId(drone.id)}
            className={`bg-white rounded-xl shadow-sm border transition-shadow cursor-pointer overflow-hidden ${selectedDroneId === drone.id ? 'border-blue-500 ring-2 ring-blue-100' : 'border-[#e0e4ef]'}`}
          >
            <div 
              className="p-4 cursor-pointer hover:bg-gray-50 flex flex-col gap-1"
              onClick={() => setExpandedDrone(expandedDrone === drone.id ? null : drone.id)}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-mono text-sm font-bold flex items-center gap-2">
                  {drone.id}
                  {/* 아이콘을 갈아끼우지 않고 회전시켜서 열림 동작과 함께 부드럽게 보이게 한다 */}
                  <span
                    className={`material-symbols-outlined text-[16px] text-gray-400 transition-transform duration-300 ease-out ${
                      expandedDrone === drone.id ? 'rotate-180' : 'rotate-0'
                    }`}
                  >
                    expand_more
                  </span>
                </span>
                {/* 배터리 자율 복귀면 'RETURNING: LOW BATTERY'(적색)로 바뀐다.
                    문구가 길어지므로 줄바꿈을 막는다. */}
                <span className={`text-[10px] px-1 py-px rounded border font-bold whitespace-nowrap ${statusStyle(drone.status, drone.currentAction).cls}`}>
                  {statusStyle(drone.status, drone.currentAction).label}
                </span>
              </div>
              <div className="flex justify-between text-[11px] text-[#424754]">
                <span>Battery</span><span>{drone.battery}%</span>
              </div>
              <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden mt-1">
                <div 
                  className={`h-full ${drone.battery <= 40 ? 'bg-red-400' : drone.battery <= 60 ? 'bg-yellow-400' : 'bg-green-400'}`} 
                  style={{ width: `${drone.battery}%` }}>
                </div>
              </div>
            </div>

            {/* 아코디언: grid-rows 0fr → 1fr 로 부드럽게 연다.
                max-height를 고정하지 않으므로 버튼 개수가 바뀌어도 높이가 알아서 맞는다.
                내부 div에 overflow-hidden이 있어야 접자 마자 내용이 잘린다. */}
            <div
              className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out ${
                expandedDrone === drone.id
                  ? 'grid-rows-[1fr] opacity-100'
                  : 'grid-rows-[0fr] opacity-0'
              }`}
            >
              <div className="overflow-hidden">
                <div className="px-4 pb-4 pt-2 border-t border-dashed border-gray-200 bg-gray-50 flex flex-col gap-2">
                {/* 드론 제어 버튼: 아래로 4층 고정 배치
                    층의 역할이 고정되어야 관제사가 위치를 외워 빠르게 누를 수 있다.
                      1층 설정  · 2층 순찰 제어(상태별로 내용이 바뀜) · 3층 종료 · 4층 비상
                    2층 첫 버튼이 한 자리에서 "순찰 시작 → 순찰 중지 → 순찰 재개"로
                    라벨만 바뀌는 것이 핵심이다.                                  */}
                {(() => {
                  const st = drone.status;
                  const offline = st === 'OFFLINE' || !st;
                  // 공중에 떠 있는 상태 — 종료·비상 층을 노출한다
                  const airborne = isAirborne(st);
                  // 배터리 자율 복귀 중에는 순찰 계열 조작을 막는다.
                  // 중지·취소는 그 자리에 계속 띄워 두고, 재개는 40%짜리를 다시 내보낸다 —
                  // 셋 다 배터리를 마저 태워 페일세이프를 사람이 무력화하는 경로가 된다.
                  const batteryRtl = isBatteryRtl(drone);

                  if (!canOperate) {
                    return (
                      <p className="text-[11px] text-gray-400 text-center py-2 bg-white rounded-lg border border-dashed border-gray-200 flex items-center justify-center gap-1">
                        <span className="material-symbols-outlined text-[14px]">visibility</span>
                        조회 전용 계정입니다
                      </p>
                    );
                  }

                  return (
                    <>
                      {/* 1층 — 설정 (경로·스테이션은 비행 중에도 갱신 가능) */}
                      <div className="grid grid-cols-2 gap-2">
                        <ControlButton
                          icon="route" label="경로지정" disabled={offline}
                          onClick={() => useDroneStore.getState().startDrawingDroneRoute(drone.id)}
                        />
                        <ControlButton
                          icon="home_pin" label="스테이션" disabled={offline}
                          onClick={() => useDroneStore.getState().startSettingStation(drone.id)}
                        />
                      </div>

                      {/* 2층 — 순찰 제어 */}
                      {offline ? (
                        <p className="text-[11px] text-gray-400 text-center py-2 bg-white rounded-lg border border-dashed border-gray-200">
                          신호가 없어 제어할 수 없습니다
                        </p>
                      ) : (
                        <div className="grid grid-cols-2 gap-2">
                          {st === 'IDLE' && (
                            <ControlButton
                              icon="play_circle" label="순찰 시작" tone="primary" full
                              onClick={() => handleStartPatrol(drone)}
                            />
                          )}
                          {st === 'PATROLLING' && (
                            <>
                              <ControlButton icon="pause_circle" label="순찰 중지" tone="warn"
                                onClick={() => pausePatrol(drone.id)} />
                              <ControlButton icon="cancel" label="순찰 취소" tone="neutral"
                                onClick={() => cancelPatrol(drone.id)} />
                            </>
                          )}
                          {st === 'PAUSED' && (
                            /* 호버링 중. 경로가 남아 있으면 "재개", 순찰 취소로 경로가 비었으면
                               재개할 것이 없으므로 새 임무를 여는 "시작"을 띄운다. */
                            drone.hasRoute === false ? (
                              <ControlButton
                                icon="play_circle" label="순찰 시작" tone="primary" full
                                onClick={() => handleStartPatrol(drone)}
                              />
                            ) : (
                              <>
                                <ControlButton icon="play_circle" label="순찰 재개" tone="primary"
                                  onClick={() => resumePatrol(drone.id)} />
                                <ControlButton icon="cancel" label="순찰 취소" tone="neutral"
                                  onClick={() => cancelPatrol(drone.id)} />
                              </>
                            )
                          )}
                          {st === 'RETURNING' && (
                            batteryRtl ? (
                              /* 사유는 배지(RETURNING: LOW BATTERY)와 알림이 말한다.
                                 이 자리가 답할 질문은 하나뿐이다 — "순찰 버튼이 왜 없지?" */
                              <p className="col-span-2 text-[11px] text-red-600 text-center py-2 bg-white rounded-lg border border-red-100">
                                배터리 부족으로 자율 복귀 중
                              </p>
                            ) : (
                              /* 복귀 중에도 정지할 수 있어야 한다. 정지하면 순찰 경로가 남은
                                 채로 호버링(PAUSED)이 되므로 거기서 '순찰 재개'로 이어갈 수 있다.
                                 (예전에는 '순찰 취소'만 띄워서 복귀 후 재개할 방법이 없었다) */
                              <>
                                <ControlButton icon="pause_circle" label="순찰 중지" tone="warn"
                                  onClick={() => pausePatrol(drone.id)} />
                                <ControlButton icon="cancel" label="순찰 취소" tone="neutral"
                                  onClick={() => cancelPatrol(drone.id)} />
                              </>
                            )
                          )}
                          {st === 'LANDING' && (
                            <p className="col-span-2 text-[11px] text-indigo-600 text-center py-2 bg-white rounded-lg border border-indigo-100">
                              착륙 중입니다
                            </p>
                          )}
                        </div>
                      )}

                      {/* 3층 — 임무 종료 (공중에 있을 때만). 복귀 중에는 첫 칸이 '순찰 재개'가 된다 */}
                      {airborne && (
                        <div className="grid grid-cols-2 gap-2">
                          {/* 이미 복귀 중이면 '복귀'는 누를 이유가 없다. 그 자리를 복귀를
                              중단하고 순찰로 돌아가는 '순찰 재개'로 바꾼다. */}
                          {batteryRtl ? (
                            /* 배터리 복귀를 순찰로 되돌리면 40%짜리가 다시 나간다.
                               자리를 비워 옆의 '안전 착륙'만 남긴다 — 더 빨리 내리는
                               조작이라 배터리 상황과 충돌하지 않는다. */
                            <span />
                          ) : st === 'RETURNING' ? (
                            <ControlButton
                              icon="play_circle" label="순찰 재개" tone="primary"
                              onClick={() => resumePatrol(drone.id)}
                            />
                          ) : (
                            <ControlButton
                              icon="home" label="순찰 복귀" tone="home"
                              disabled={st === 'LANDING'}
                              onClick={async () => {
                                await returnToBase(drone.id);
                              }}
                            />
                          )}
                          <ControlButton
                            icon="flight_land" label="안전 착륙" tone="land"
                            disabled={st === 'LANDING'}
                            onClick={() => landPatrol(drone.id)}
                          />
                        </div>
                      )}

                      {/* 실시간 영상 — 지상에서도 카메라를 볼 수 있어야 하므로
                          공중 여부와 무관하게 연결만 되어 있으면 띄운다. */}
                      {!offline && (
                        <ControlButton
                          icon="videocam" label="실시간 영상" tone="neutral" full
                          onClick={() => openLiveStream(drone.id)}
                        />
                      )}

                      {/* 4층 — 비상 (공중에 있을 때만, 단독 배치로 오조작 방지) */}
                      {airborne && (
                        <ControlButton
                          icon="emergency" label="비상 정지" tone="danger" full
                          onClick={() => openCancelModal(drone.id)}
                        />
                      )}
                    </>
                  );
                })()}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
      
      <div className="mt-6 px-1 border-t border-[#c2c6d6] pt-4">
        <div 
          className="flex justify-between items-center px-3 cursor-pointer mb-2"
          onClick={() => setIsRegisteredExpanded(!isRegisteredExpanded)}
        >
          <h3 className="text-xs font-medium text-[#727785] uppercase tracking-widest flex items-center gap-1">
            Registered DB <span className="text-[10px] bg-gray-200 px-1.5 py-0.5 rounded-full text-gray-600">{registeredDrones.length}</span>
          </h3>
          <span
            className={`material-symbols-outlined text-gray-400 text-[18px] transition-transform duration-300 ease-out ${
              isRegisteredExpanded ? 'rotate-180' : 'rotate-0'
            }`}
          >
            expand_more
          </span>
        </div>

        {/* 위 드론 카드와 같은 아코디언 방식. 안쪽 목록은 자체 스크롤을 유지한다. */}
        <div
          className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out ${
            isRegisteredExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
          }`}
        >
          <div className="overflow-hidden">
          <div className="space-y-1.5 max-h-[150px] overflow-y-auto [scrollbar-gutter:stable] pr-1">
            {registeredDrones.length > 0 ? registeredDrones.map(dbDrone => (
              <div key={dbDrone.droneId} className="bg-white p-2.5 rounded border border-gray-200 text-xs flex justify-between items-center">
                <div className="flex flex-col">
                  <span className="font-semibold text-gray-700">{dbDrone.droneId}</span>
                  <span className="text-[10px] text-gray-400">{dbDrone.droneName}</span>
                </div>
                {/* 텔레메트리로 이미 활성화된 드론인지 확인 */}
                {drones.some(d => d.id === dbDrone.droneId && d.status !== 'OFFLINE') ? (
                  <span className="w-2 h-2 rounded-full bg-green-500" title="Online"></span>
                ) : (
                  <span className="w-2 h-2 rounded-full bg-gray-300" title="Offline"></span>
                )}
              </div>
            )) : (
              <div className="text-xs text-gray-400 text-center py-2">등록된 드론이 없습니다</div>
            )}
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}
