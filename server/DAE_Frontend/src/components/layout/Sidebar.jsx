import React, { useState, useEffect, useMemo } from 'react';
import useDroneStore from '../../store/useDroneStore';
import useUserStore from '../../store/useUserStore';
import { startPatrol, cancelPatrol, pausePatrol, returnToBase, landPatrol, saveStation, getUserDroneSettings } from '../../services/api';
import toast from 'react-hot-toast';
import DroneStatus from './DroneStatus';

export default function Sidebar() {
  const drones = useDroneStore((state) => state.drones);
  const isRouteManagerOpen = useDroneStore((state) => state.isRouteManagerOpen);
  const isDroneStatusOpen = useDroneStore((state) => state.isDroneStatusOpen);
  const isRegisterModalOpen = useDroneStore((state) => state.isRegisterModalOpen);
  const hasUnsavedChanges = useDroneStore((state) => state.hasUnsavedChanges);
  const droneSettings = useDroneStore((state) => state.droneSettings);
  const setDroneSettings = useDroneStore((state) => state.setDroneSettings);

  const activeMenu = isRouteManagerOpen ? 'route' :
                     isDroneStatusOpen ? 'status' :
                     isRegisterModalOpen ? 'management' : 'fleet';

  const handleMenuSwitch = (action) => {
    const dStore = useDroneStore.getState();
    if (hasUnsavedChanges || dStore.isDrawingRoute) {
      if (!window.confirm("작성 중인 내용이 지워집니다. 이동하시겠습니까?")) {
        return;
      }
      dStore.setHasUnsavedChanges(false);
    }

    const uStore = useUserStore.getState();
    
    dStore.setRouteManagerOpen(false);
    dStore.setDroneStatusOpen(false);
    if (dStore.isRegisterModalOpen) dStore.closeRegisterModal();
    if (dStore.isDrawingRoute) dStore.stopDrawingRoute();
    if (dStore.isSettingStation) dStore.stopSettingStation();
    
    if (uStore.isHistoryOpen && uStore.closeHistory) uStore.closeHistory();
    if (uStore.isAccountModalOpen && uStore.closeAccountModal) uStore.closeAccountModal();

    if (action) action();
  };

  useEffect(() => {
    // 설정 기반 데이터만 fetch
    const fetchSettings = async () => {
      try {
        const res = await getUserDroneSettings();
        setDroneSettings(res);
      } catch (error) {
        console.error("Failed to fetch drone settings:", error);
      }
    };
    fetchSettings();
  }, []);

  // 설정 기반 필터 및 정렬
  const safeSettings = Array.isArray(droneSettings) ? droneSettings : [];
  const displayDrones = [...drones].filter(d => {
    const s = safeSettings.find(set => set.droneId === d.id);
    return s ? s.visible : true; // 기본값은 표시
  }).sort((a, b) => {
    const sa = safeSettings.find(set => set.droneId === a.id);
    const sb = safeSettings.find(set => set.droneId === b.id);
    const oa = sa ? sa.sortOrder : 999;
    const ob = sb ? sb.sortOrder : 999;
    return oa - ob;
  });

  return (
    <aside className="hidden md:flex flex-col h-full w-[280px] py-6 px-4 gap-2 bg-[#f8f9ff] border-r border-[#c2c6d6] shrink-0">
      <div className="px-4 mb-6 flex justify-between items-start">
        <div>
          <h2 className="text-lg font-semibold text-[#0058be]">System Active</h2>
          <p className="text-xs font-medium text-[#424754]">All units online</p>
        </div>
      </div>
      <nav className="flex-none flex flex-col gap-1">
        <button 
          onClick={() => handleMenuSwitch(null)}
          className={`flex items-center gap-4 p-4 w-full text-left rounded-lg transition-transform duration-200 active:translate-x-1 ${
            activeMenu === 'fleet' ? 'bg-[#dae2fd] text-[#5c647a]' : 'text-[#424754] hover:bg-[#e5eeff]'
          }`}>
          <span className="material-symbols-outlined" style={{ fontVariationSettings: activeMenu === 'fleet' ? "'FILL' 1" : "'FILL' 0" }}>grid_view</span>
          <span className="text-sm font-medium">Fleet</span>
        </button>
        <button 
          onClick={() => handleMenuSwitch(() => useDroneStore.getState().setRouteManagerOpen(true))}
          className={`flex items-center gap-4 p-4 w-full text-left rounded-lg transition-all duration-200 active:translate-x-1 ${
            activeMenu === 'route' ? 'bg-[#dae2fd] text-[#5c647a]' : 'text-[#424754] hover:bg-[#e5eeff]'
          }`}>
          <span className="material-symbols-outlined" style={{ fontVariationSettings: activeMenu === 'route' ? "'FILL' 1" : "'FILL' 0" }}>route</span>
          <span className="text-sm font-medium">Patrol Routes</span>
        </button>
        <button 
          onClick={() => handleMenuSwitch(() => useDroneStore.getState().setDroneStatusOpen(true))}
          className={`flex items-center gap-4 p-4 w-full text-left rounded-lg transition-all duration-200 active:translate-x-1 ${
            activeMenu === 'status' ? 'bg-[#dae2fd] text-[#5c647a]' : 'text-[#424754] hover:bg-[#e5eeff]'
          }`}>
          <span className="material-symbols-outlined" style={{ fontVariationSettings: activeMenu === 'status' ? "'FILL' 1" : "'FILL' 0" }}>analytics</span>
          <span className="text-sm font-medium">Drone Status</span>
        </button>
        <button 
          onClick={() => handleMenuSwitch(() => useDroneStore.getState().openRegisterModal())}
          className={`flex items-center gap-4 p-4 w-full text-left rounded-lg transition-all duration-200 active:translate-x-1 ${
            activeMenu === 'management' ? 'bg-[#dae2fd] text-[#5c647a]' : 'text-[#424754] hover:bg-[#e5eeff]'
          }`}>
          <span className="material-symbols-outlined" style={{ fontVariationSettings: activeMenu === 'management' ? "'FILL' 1" : "'FILL' 0" }}>settings_suggest</span>
          <span className="text-sm font-medium">Drone Management</span>
        </button>
      </nav>
      
      <DroneStatus />
    </aside>
  );
}
