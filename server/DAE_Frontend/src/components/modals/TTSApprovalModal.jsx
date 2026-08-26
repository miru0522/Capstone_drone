import React, { useState, useEffect } from 'react';
import useDroneStore from '../../store/useDroneStore';
import { resumePatrol, returnToBase, approveTTS } from '../../services/api';
import { getApiBaseUrl } from '../../config';

export default function TTSApprovalModal() {
  const { isOpen, alertId } = useDroneStore((state) => state.ttsModal);
  const [isMuted, setIsMuted] = useState(true);
  const [step, setStep] = useState(1);
  const currentAlert = useDroneStore((state) => 
    state.alerts.find(a => a.id === alertId)
  );
  const closeTTSModal = useDroneStore((state) => state.closeTTSModal);
  const resolveAlert = useDroneStore((state) => state.resolveAlert);

  useEffect(() => {
    if (isOpen) {
      setStep(1);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleResumePatrol = async () => {
    console.log("순찰 재개 버튼 클릭. 현재 경보 데이터:", currentAlert);
    
    // 시뮬레이터/이벤트 데이터에 droneId가 누락된 경우 "DR-01"을 기본값으로 사용
    const targetId = currentAlert?.droneId || "DR-01";
    
    if (!currentAlert?.droneId) {
      console.warn("⚠️ 경보 데이터에 droneId가 없어 'DR-01'로 임시 강제 전송합니다.");
    }
    
    try {
      await resumePatrol(targetId);
      console.log(`[STOMP] 드론 ${targetId} 순찰 재개 명령 전송 완료!`);
      } catch (error) {
        console.error("[STOMP] 순찰 재개 실패", error);
        alert("순찰 재개 명령 중 에러가 발생했습니다.");
      } finally {
        resolveAlert(alertId);
        closeTTSModal();
      }
  };

  /**
   * 경보를 방송 없이 닫는다. 「확인」·「무시」·「거절 (무시)」가 공유한다.
   *
   * ⚠️ 예전에는 여기서 startPatrol을 보냈다. 관제사가 경보를 확인했을 뿐인데
   *    드론이 출발했고, 대기 중이던 기체가 갑자기 날아갔다.
   *    게다가 START_PATROL이라 경로를 처음부터 다시 돌았다(이어서 하려면 RESUME_PATROL).
   *    경보를 닫는 것과 드론을 조작하는 것은 별개여야 한다.
   *    순찰을 이어가려면 이 모달의 「순찰 재개」 버튼이 따로 있다.
   */
  const handleReject = () => {
    resolveAlert(alertId);
    closeTTSModal();
  };

  const handleApproveTTS = async () => {
    try {
      await approveTTS(alertId);
      setStep(2);
    } catch (error) {
      console.error(error);
      alert("경고 방송 송출 중 에러가 발생했습니다.");
    }
  };

  const handleReturnToBase = async () => {
    console.log("순찰 복귀 버튼 클릭. 현재 경보 데이터:", currentAlert);
    
    const targetId = currentAlert?.droneId || "DR-01";
    
    if (!currentAlert?.droneId) {
      console.warn("⚠️ 경보 데이터에 droneId가 없어 'DR-01'로 임시 강제 전송합니다.");
    }

    try {
      await returnToBase(targetId);
      console.log(`[STOMP] 드론 ${targetId} 순찰 복귀 명령 전송 완료!`);
      
      resolveAlert(alertId);
      closeTTSModal();
    } catch (e) {
      console.error(e);
      alert("순찰 복귀 명령 실패");
    }
  };

  const handleDrawRoute = () => {
    if (currentAlert?.droneId) {
      useDroneStore.getState().startDrawingDroneRoute(currentAlert.droneId);
      resolveAlert(alertId);
      closeTTSModal();
    }
  };

  const isInfo = currentAlert?.actionType === 'PATROL_DONE' || currentAlert?.type === 'Info';
  const isReturnDone = currentAlert?.actionType === 'RETURN_DONE';
  const isBattery = currentAlert?.actionType === 'BATTERY';

  return (
    <div className="absolute inset-0 flex items-center justify-center z-[100] bg-black/10 backdrop-blur-[2px]">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl p-6 relative animate-in zoom-in-95 duration-200">
        {/* 기존 모달 5개와 같은 자리·모양. 조작을 강요하지 않고 그냥 닫을 수 있어야 한다. */}
        <button
          type="button"
          onClick={closeTTSModal}
          aria-label="닫기"
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined">close</span>
        </button>

        
        <div className="flex items-center gap-3 mb-2">
          {isInfo ? (
            <div className="p-2 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center">
              <span className="material-symbols-outlined">check_circle</span>
            </div>
          ) : isBattery ? (
            <div className="p-2 bg-orange-100 text-orange-600 rounded-full flex items-center justify-center">
              <span className="material-symbols-outlined animate-pulse">battery_alert</span>
            </div>
          ) : (
            <div className="p-2 bg-red-100 text-red-600 rounded-full flex items-center justify-center">
              <span className="material-symbols-outlined animate-pulse">record_voice_over</span>
            </div>
          )}
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              {isReturnDone ? '스테이션 복귀 완료' :
               isInfo ? '순찰 완료 안내' : 
               isBattery ? '배터리 경고 (40% 이하)' : 
               step === 1 ? '이상 상황 발생 (경고 방송 대기 중)' : '이상 상황 발생 (경고 방송 송출 완료)'}
            </h2>
            <p className="text-xs text-gray-500 font-medium">
              {isReturnDone ? 'Return to Base Completed - Drone Docked' :
               isInfo ? 'Routine Patrol Completed - Status Normal' : 
               isBattery ? 'Low Battery Alert - Action Required' : 
               step === 1 ? 'Level 4 Priority Incident - Awaiting Authorization' : 'Level 4 Priority Incident - Broadcast Completed'}
            </p>
          </div>
        </div>

        <hr className="my-4 border-gray-200" />
        
        {currentAlert && (
          <div className="mb-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="material-symbols-outlined text-red-600 text-sm">emergency</span>
              <p className="text-sm font-bold text-gray-900">감지 이벤트: {currentAlert.title}</p>
            </div>
            
            {currentAlert.videoUrl ? (
              <div className="relative w-full h-48 bg-black rounded-lg border border-gray-200 overflow-hidden shadow-inner group mb-4">
                <video src={currentAlert.videoUrl.startsWith('http') ? currentAlert.videoUrl : `${getApiBaseUrl()}${currentAlert.videoUrl}`} crossOrigin="anonymous" autoPlay loop muted={isMuted} className="w-full h-full object-cover" />
                <button
                  onClick={() => setIsMuted(!isMuted)}
                  className="absolute bottom-2 right-2 p-2 bg-black/50 hover:bg-black/80 rounded-full text-white transition-all opacity-0 group-hover:opacity-100 flex items-center justify-center backdrop-blur-sm"
                  title="음소거 토글"
                >
                  <span className="material-symbols-outlined text-sm">{isMuted ? 'volume_off' : 'volume_up'}</span>
                </button>
              </div>
            ) : (
              <img src={currentAlert.img} alt="Snapshot" className="w-full h-32 object-cover rounded-lg border border-gray-200 mb-4" />
            )}

            {!isInfo && !isReturnDone && !isBattery && (
              <div className="bg-blue-50/50 rounded-lg p-3 border border-blue-100 mb-3 shadow-sm">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="material-symbols-outlined text-blue-600 text-[16px]">analytics</span>
                  <span className="text-xs font-bold text-blue-900">AI 상황 분석 리포트 (VLM)</span>
                </div>
                <p className="text-sm text-gray-700 leading-relaxed font-medium break-keep">{currentAlert.desc}</p>
              </div>
            )}
          </div>
        )}

        {!isInfo && !isReturnDone && !isBattery && (step === 1 || step === 2) && (
          <div className="bg-red-50/30 rounded-lg p-3 mb-6 border border-red-200 border-dashed shadow-sm">
             <div className="flex items-center gap-1.5 mb-1.5">
                <span className="material-symbols-outlined text-red-500 text-[16px]">campaign</span>
                <span className="text-xs font-bold text-red-800">{step === 2 ? '송출 완료된 자동 경고 방송' : '송출 예정인 자동 경고 방송'}</span>
             </div>
            <p className="text-gray-800 italic text-sm font-semibold leading-relaxed">"{currentAlert.ttsText || '경고: 허가되지 않은 접근이 감지되었습니다. 즉시 퇴거해 주시기 바랍니다.'}"</p>
          </div>
        )}
        
        <div className="flex gap-4 justify-end mt-4">
          {isReturnDone ? (
            <button 
              onClick={handleReject} 
              className="px-6 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 shadow-sm transition-colors"
            >
              확인
            </button>
          ) : isInfo ? (
            <>
              <button 
                onClick={handleDrawRoute} 
                className="px-6 py-2 rounded-lg text-sm font-medium text-gray-600 border border-gray-300 hover:bg-gray-50 transition-colors"
              >
                경로 지정
              </button>
              <button 
                onClick={handleReturnToBase} 
                className="px-6 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 shadow-sm transition-colors"
              >
                순찰 복귀
              </button>
            </>
          ) : isBattery ? (
            <>
              <button 
                onClick={handleReject} 
                className="px-6 py-2 rounded-lg text-sm font-medium text-gray-600 border border-gray-300 hover:bg-gray-50 transition-colors"
              >
                무시
              </button>
              <button 
                onClick={handleReturnToBase} 
                className="px-6 py-2 rounded-lg text-sm font-medium bg-orange-600 text-white hover:bg-orange-700 shadow-sm transition-colors"
              >
                순찰 복귀
              </button>
            </>
          ) : (
            <>
              {step === 1 ? (
                <>
                  <button 
                    onClick={handleReject} 
                    className="px-6 py-2 rounded-lg text-sm font-medium text-gray-600 border border-gray-300 hover:bg-gray-50 transition-colors"
                  >
                    거절 (무시)
                  </button>
                  <button 
                    onClick={handleApproveTTS} 
                    className="px-6 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700 shadow-sm transition-colors"
                  >
                    경고 방송 송출
                  </button>
                </>
              ) : (
                <>
                  <button 
                    onClick={handleReturnToBase} 
                    className="px-6 py-2 rounded-lg text-sm font-medium text-gray-600 border border-gray-300 hover:bg-gray-50 transition-colors"
                  >
                    순찰 복귀
                  </button>
                  <button 
                    onClick={handleResumePatrol} 
                    className="px-6 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700 shadow-sm transition-colors"
                  >
                    순찰 재개
                  </button>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
