import React, { useState, useEffect } from 'react';
import useDroneStore from '../../store/useDroneStore';
import { registerDrone } from '../../services/api';

export default function DroneRegisterModal() {
  const isRegisterModalOpen = useDroneStore((state) => state.isRegisterModalOpen);
  const closeRegisterModal = useDroneStore((state) => state.closeRegisterModal);
  const updateDroneData = useDroneStore((state) => state.updateDroneData);
  const setHasUnsavedChanges = useDroneStore((state) => state.setHasUnsavedChanges);

  const [droneName, setDroneName] = useState('');
  const [droneId, setDroneId] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!isRegisterModalOpen) {
      setDroneName('');
      setDroneId('');
      setError(null);
      setHasUnsavedChanges(false);
    }
  }, [isRegisterModalOpen, setHasUnsavedChanges]);

  if (!isRegisterModalOpen) return null;

  const handleClose = () => {
    setHasUnsavedChanges(false);
    setDroneName('');
    setDroneId('');
    setError(null);
    closeRegisterModal();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!droneName || !droneId) {
      setError("이름과 드론 ID를 모두 입력해주세요.");
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      
      const formData = new FormData();
      formData.append('droneName', droneName);
      formData.append('droneId', droneId);
      
      await registerDrone(formData);
      
      // 등록 성공 시 임시로 화면에 띄우기 (실제 데이터는 STOMP로 갱신됨)
      updateDroneData({
        id: droneId,
        status: 'OFFLINE',
        battery: 100,
        lat: 0,
        lng: 0,
        altitude: 0
      });

      setDroneName('');
      setDroneId('');
      setHasUnsavedChanges(false);
      closeRegisterModal();
    } catch (err) {
      console.error(err);
      setError("등록에 실패했습니다. 서버를 확인해주세요.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-white w-[400px] rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-100 bg-gray-50">
          <div className="flex items-center gap-2 text-blue-700">
            <span className="material-symbols-outlined text-2xl">add_circle</span>
            <h2 className="text-lg font-bold">드론 추가 등록</h2>
          </div>
          <button 
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-700 transition-colors"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {error && (
            <div className="mb-4 p-3 bg-red-50 text-red-600 text-sm font-medium rounded-lg border border-red-100">
              {error}
            </div>
          )}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-bold text-gray-700">드론 이름 (표시명)</label>
              <input 
                type="text" 
                value={droneName}
                onChange={(e) => {
                  setDroneName(e.target.value);
                  setHasUnsavedChanges(true);
                }}
                placeholder="예: 정찰용 드론 1호"
                className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-sm"
              />
            </div>
            
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-bold text-gray-700">드론 ID</label>
              <input 
                type="text" 
                value={droneId}
                onChange={(e) => {
                  setDroneId(e.target.value);
                  setHasUnsavedChanges(true);
                }}
                placeholder="예: DR-01"
                className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-sm font-mono"
              />
              <p className="text-xs text-gray-500 mt-1">
                드론이 텔레메트리로 보내는 droneId 값과 정확히 일치해야 합니다.
              </p>
            </div>

            <div className="flex gap-3 mt-4">
              <button 
                type="button"
                onClick={handleClose}
                className="flex-1 py-3 bg-white border border-gray-200 text-gray-700 rounded-xl font-bold hover:bg-gray-50 transition-colors shadow-sm text-sm"
              >
                취소
              </button>
              <button 
                type="submit"
                disabled={isLoading}
                className="flex-1 py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-colors shadow-md shadow-blue-500/20 text-sm flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isLoading ? (
                  <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
                ) : (
                  <span className="material-symbols-outlined text-[18px]">check</span>
                )}
                {isLoading ? '등록 중...' : '드론 등록'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
