import React from 'react';
import useDroneStore from '../../store/useDroneStore';
import { landPatrol, returnToBase } from '../../services/api';

/**
 * 임무를 마치고 공중에서 대기 중인 드론에 다음 지시를 묻는다.
 *
 * 드론은 순찰을 완주해도, 스테이션에 복귀해도 스스로 내려앉지 않는다.
 * 관제사가 판단하기 전에 기체가 지상으로 내려가면 다시 띄우는 데 시간이 걸리고,
 * 착륙 지점이 안전한지도 사람이 확인해야 하기 때문이다.
 * 그래서 착륙을 지시할 통로가 필요하다.
 */
export default function MissionDoneModal() {
  const { isOpen, droneId, kind, alertId } = useDroneStore((state) => state.missionDoneModal);
  const closeMissionDoneModal = useDroneStore((state) => state.closeMissionDoneModal);
  const resolveAlert = useDroneStore((state) => state.resolveAlert);

  if (!isOpen) return null;

  const isPatrol = kind === 'patrol';

  const run = async (fn, failMsg) => {
    try {
      await fn(droneId);
      // 조치가 끝났으므로 알림 패널의 해당 항목을 회색(RESOLVED)으로 넘긴다.
      if (alertId) resolveAlert(alertId);
      closeMissionDoneModal();
    } catch (e) {
      console.error(e);
      alert(failMsg);
    }
  };

  return (
    <div className="absolute inset-0 flex items-center justify-center z-[110] bg-black/20 backdrop-blur-[2px]">
      <div className="bg-white w-full max-w-sm rounded-2xl shadow-2xl p-6 relative animate-in zoom-in-95 duration-200">
        <button
          type="button"
          onClick={closeMissionDoneModal}
          aria-label="닫기"
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined">close</span>
        </button>

        <div className="flex items-center gap-3 mb-2">
          <div className={`p-2 rounded-full flex items-center justify-center ${
            isPatrol ? 'bg-green-100 text-green-600' : 'bg-blue-100 text-blue-600'
          }`}>
            <span className="material-symbols-outlined">{isPatrol ? 'task_alt' : 'drone'}</span>
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              {isPatrol ? '순찰 임무 완료' : '스테이션 복귀 완료'}
            </h2>
            <p className="text-xs text-gray-500 font-medium">
              {droneId} 드론이 공중에서 대기 중입니다.
            </p>
          </div>
        </div>

        <hr className="my-4 border-gray-200" />

        <p className="text-sm text-gray-700 mb-6">
          {isPatrol
            ? '지정된 경로를 모두 돌았습니다. 다음 행동을 선택해 주세요.'
            : '스테이션 상공에 도착했습니다. 다음 행동을 선택해 주세요.'}
          <span className="block text-xs text-gray-500 mt-2">
            닫아도 드론은 그대로 대기합니다. 사이드바에서 언제든 지시할 수 있습니다.
          </span>
        </p>

        <div className="flex gap-3 justify-end">
          {isPatrol && (
            <button
              onClick={() => run(returnToBase, '복귀 명령에 실패했습니다.')}
              className="px-4 py-2 rounded-lg text-sm font-medium text-blue-700 bg-blue-50 border border-blue-200 hover:bg-blue-100 transition-colors"
            >
              스테이션 복귀
            </button>
          )}
          <button
            onClick={() => run(landPatrol, '착륙 명령에 실패했습니다.')}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 shadow-sm transition-colors"
          >
            안전 착륙
          </button>
        </div>
      </div>
    </div>
  );
}
