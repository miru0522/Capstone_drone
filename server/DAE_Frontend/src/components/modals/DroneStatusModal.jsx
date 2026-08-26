import React from 'react';
import useDroneStore from '../../store/useDroneStore';
import { statusStyle } from '../../utils/droneStatus';

export default function DroneStatusModal() {
  const isOpen = useDroneStore((state) => state.isDroneStatusOpen);
  const setDroneStatusOpen = useDroneStore((state) => state.setDroneStatusOpen);
  const drones = useDroneStore((state) => state.drones);

  if (!isOpen) return null;

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center p-4 bg-[#0b1c30]/40 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="bg-[#f8f9ff] rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200 border border-[#c2c6d6]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 bg-white border-b border-[#e5e7eb] shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#dae2fd] text-[#0058be] rounded-lg">
              <span className="material-symbols-outlined block">analytics</span>
            </div>
            <div>
              <h2 className="text-xl font-bold text-[#0b1c30]">Drone Fleet Status</h2>
              <p className="text-sm text-[#424754] mt-1">실시간 드론 비행 상태 및 배터리 모니터링</p>
            </div>
          </div>
          <button 
            onClick={() => setDroneStatusOpen(false)}
            className="p-2 text-[#424754] hover:bg-red-50 hover:text-red-600 rounded-full transition-colors flex items-center justify-center"
          >
            <span className="material-symbols-outlined text-[24px]">close</span>
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-auto p-6">
          {drones.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-4 text-gray-400">
              <span className="material-symbols-outlined text-5xl">drone</span>
              <p className="font-medium">현재 등록되거나 비행 중인 드론이 없습니다.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {drones.map((drone) => (
                <div key={drone.id} className="bg-white rounded-xl shadow-sm border border-[#e5e7eb] overflow-hidden hover:shadow-md transition-shadow">
                  {/* Card Header */}
                  <div className="p-4 border-b border-[#e5e7eb] bg-gray-50 flex justify-between items-center">
                    <div className="flex items-center gap-3">
                      <span className="material-symbols-outlined text-[#0058be] text-3xl">drone</span>
                      <div>
                        <h3 className="font-mono font-bold text-lg text-[#0b1c30]">{drone.id}</h3>
                        <p className="text-[11px] text-[#727785] tracking-wider uppercase">Current Unit</p>
                      </div>
                    </div>
                    <span className={`px-3 py-1 rounded-full text-xs font-bold border whitespace-nowrap ${statusStyle(drone.status, drone.currentAction).cls}`}>
                      {statusStyle(drone.status, drone.currentAction).label}
                    </span>
                  </div>

                  {/* Card Body */}
                  <div className="p-5 space-y-5">
                    {/* Battery */}
                    <div>
                      <div className="flex justify-between items-end mb-2">
                        <span className="text-sm font-semibold text-[#424754] flex items-center gap-1">
                          <span className="material-symbols-outlined text-[18px]">battery_charging_full</span>
                          Battery Level
                        </span>
                        <span className={`font-mono font-bold text-lg ${drone.battery <= 40 ? 'text-red-400' : drone.battery <= 60 ? 'text-yellow-400' : 'text-green-400'}`}>
                          {drone.battery}%
                        </span>
                      </div>
                      <div className="w-full bg-[#e5eeff] h-3 rounded-full overflow-hidden shadow-inner">
                        <div 
                          className={`h-full transition-all duration-500 ease-out ${drone.battery <= 40 ? 'bg-red-400' : drone.battery <= 60 ? 'bg-yellow-400' : 'bg-green-400'}`} 
                          style={{ width: `${drone.battery}%` }}
                        />
                      </div>
                    </div>

                    {/* Telemetry Data */}
                    <div className="grid grid-cols-2 gap-4 pt-2 border-t border-[#e5e7eb]">
                      <div className="bg-[#f8f9ff] p-3 rounded-lg border border-[#e5eeff]">
                        <p className="text-[11px] text-[#727785] font-bold uppercase mb-1">Altitude</p>
                        <p className="font-mono text-base font-medium text-[#0b1c30]">{drone.altitude} m</p>
                      </div>
                      <div className="bg-[#f8f9ff] p-3 rounded-lg border border-[#e5eeff]">
                        <p className="text-[11px] text-[#727785] font-bold uppercase mb-1">GPS (Lat, Lng)</p>
                        {/* 등록만 하고 텔레메트리를 받은 적 없는 드론은 lat/lng이 null이다.
                            값 없이 toFixed를 부르면 TypeError로 React 트리 전체가 죽는다. */}
                        <p className="font-mono text-[11px] text-[#0b1c30] break-all">
                          {typeof drone.lat === 'number' && typeof drone.lng === 'number'
                            ? `${drone.lat.toFixed(6)}, ${drone.lng.toFixed(6)}`
                            : '-'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
