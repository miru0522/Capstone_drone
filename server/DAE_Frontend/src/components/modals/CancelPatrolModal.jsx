import React from 'react';
import useDroneStore from '../../store/useDroneStore';
import { emergencyStop } from '../../services/api';

export default function CancelPatrolModal() {
  const { isOpen, droneId } = useDroneStore((state) => state.cancelModal);
  const closeCancelModal = useDroneStore((state) => state.closeCancelModal);

  if (!isOpen) return null;

  const handleCancel = async () => {
    try {
      await emergencyStop(droneId);
      closeCancelModal();
    } catch (e) {
      console.error(e);
      alert("비상 정지(모터 차단) 명령 전송에 실패했습니다.");
    }
  };

  return (
    <div className="absolute inset-0 flex items-center justify-center z-[110] bg-black/20 backdrop-blur-[2px]">
      <div className="bg-white w-full max-w-sm rounded-2xl shadow-2xl p-6 relative animate-in zoom-in-95 duration-200">
        {/* 기존 모달 5개와 같은 자리·모양. 조작을 강요하지 않고 그냥 닫을 수 있어야 한다. */}
        <button
          type="button"
          onClick={closeCancelModal}
          aria-label="닫기"
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined">close</span>
        </button>

        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-red-100 text-red-600 rounded-full flex items-center justify-center">
            <span className="material-symbols-outlined">emergency</span>
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">비상 강제 종료</h2>
            <p className="text-xs text-gray-500 font-medium">{droneId} 드론의 모든 동작을 멈춥니다.</p>
          </div>
        </div>

        <hr className="my-4 border-gray-200" />
        
        {/* 이 모달은 CANCEL_PATROL이 아니라 EMERGENCY_STOP(모터 차단)을 보낸다.
            파일·함수 이름이 "Cancel"인 것은 과거에 CANCEL_PATROL이 Kill Switch였던 시절의 잔재다.
            문구는 실제 동작(Disarm)을 기준으로 적는다. */}
        <p className="text-sm text-gray-700 mb-6 leading-relaxed">
          정말 <span className="font-bold">{droneId}</span>의 모터를 차단하시겠습니까?<br/>
          <span className="text-red-500 font-bold bg-red-50 px-1 mt-1 inline-block">공중일 경우 모터가 정지되어 드론이 추락합니다.</span>
          <span className="block text-xs text-gray-500 mt-2">
            순찰만 멈추려면 이 창을 닫고 <b>순찰 중지</b> 또는 <b>순찰 취소</b>를 사용하십시오.
          </span>
        </p>

        <div className="flex gap-3 justify-end">
          <button 
            onClick={closeCancelModal} 
            className="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-50 border border-gray-200 hover:bg-gray-100 transition-colors"
          >
            뒤로가기
          </button>
          <button 
            onClick={handleCancel} 
            className="px-4 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700 shadow-sm transition-colors"
          >
            모터 차단
          </button>
        </div>
      </div>
    </div>
  );
}
