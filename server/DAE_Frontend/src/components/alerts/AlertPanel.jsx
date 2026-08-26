import React from 'react';
import useDroneStore from '../../store/useDroneStore';
import { getApiBaseUrl } from '../../config';

export default function AlertPanel() {
  const alerts = useDroneStore((state) => state.alerts);
  const openTTSModal = useDroneStore((state) => state.openTTSModal);
  const dismissAlert = useDroneStore((state) => state.dismissAlert);
  const dismissed = useDroneStore((state) => state.dismissed);
  const restoreDismissed = useDroneStore((state) => state.restoreDismissed);
  const openMissionDoneModal = useDroneStore((state) => state.openMissionDoneModal);

  // 알림 종류에 따라 다시 열 팝업이 다르다.
  //   VLM 경보        → TTS 승인
  //   순찰·복귀 완료  → 안전 착륙 지시
  //   배터리 경고     → 조치 팝업 없음 (알림으로 끝)
  const DONE_KIND = { PATROL_DONE: 'patrol', RETURN_DONE: 'return' };
  const reopen = (alert) => {
    const kind = DONE_KIND[alert.actionType];
    if (kind) openMissionDoneModal(alert.droneId, kind, alert.id);
    else if (alert.source !== 'System') openTTSModal(alert.id);
  };
  const canReopen = (alert) => !!DONE_KIND[alert.actionType] || alert.source !== 'System';
  const isAlertPanelOpen = useDroneStore((state) => state.isAlertPanelOpen);

  return (
    <aside className={`bg-[#f8f9ff] border-l border-[#c2c6d6] flex flex-col overflow-hidden shrink-0 transition-all duration-300 ease-in-out ${isAlertPanelOpen ? 'w-[340px] opacity-100' : 'w-0 opacity-0 border-none'}`}>
      <div className="p-6 border-b border-[#c2c6d6] bg-[#f8f9ff] w-[340px]">
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-semibold text-[#0b1c30]">Real-time VLM Alerts</h3>
          <span className="flex h-2 w-2 rounded-full bg-red-600 animate-pulse"></span>
        </div>
        {/* X는 지우는 것이 아니라 접어두는 것이다. 조치를 다시 하려면 되살릴 통로가 있어야 한다. */}
        {dismissed.length > 0 && (
          <button
            type="button"
            onClick={restoreDismissed}
            className="mt-3 w-full flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs font-bold text-[#0058be] bg-white border border-[#c2c6d6] hover:bg-blue-50 transition-colors"
          >
            <span className="material-symbols-outlined text-sm">unarchive</span>
            숨긴 알림 {dismissed.length}개 다시 보기
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {alerts.map((alert) => (
          <div 
            key={alert.id} 
            className={`p-4 border rounded-xl shadow-sm transition-all duration-300 ${canReopen(alert) ? 'cursor-pointer' : ''} ${
              alert.status === 'RESOLVED' 
                ? 'bg-[#e5e7eb] border-gray-300 opacity-60 grayscale hover:opacity-100 hover:grayscale-0' 
                : 'bg-white border-[#c2c6d6] hover:shadow-md'
            }`}
            // X로 접어뒀다가 되살린 알림도 여기서 다시 조치할 수 있어야 한다.
            onClick={() => { if (canReopen(alert)) reopen(alert); }}
          >
            <div className="flex justify-between items-start mb-2">
              <div className={`px-2 py-1 rounded text-[10px] font-bold uppercase ${
                alert.type === 'Critical' ? 'bg-red-100 text-red-600' : 
                alert.type === 'Info' ? 'bg-green-100 text-green-700' : 
                'bg-yellow-100 text-yellow-700'
              }`}>
                {alert.type}
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-[#727785]">{alert.time}</span>
                {/* 닫아도 VLM 경보는 event_logs에 남는다. HISTORY에서 이어서 조치할 수 있다. */}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); dismissAlert(alert.id); }}
                  title="알림 닫기"
                  className="text-[#9aa0b0] hover:text-[#0b1c30] hover:bg-black/5 rounded transition-colors leading-none p-0.5"
                >
                  <span className="material-symbols-outlined text-base align-middle">close</span>
                </button>
              </div>
            </div>
            <div className="flex gap-4">
              <div className={`w-16 h-16 rounded-lg overflow-hidden shrink-0 border border-[#c2c6d6] ${alert.videoUrl ? 'bg-black' : ''}`}>
                {alert.videoUrl ? (
                  <video 
                    src={alert.videoUrl.startsWith('http') ? alert.videoUrl : `${getApiBaseUrl()}${alert.videoUrl}`} 
                    className="w-full h-full object-cover"
                    autoPlay 
                    loop 
                    muted 
                    playsInline
                    crossOrigin="anonymous"
                    onLoadStart={() => console.log('[비디오 디버그] 로드 시작:', alert.videoUrl)}
                    onLoadedMetadata={() => console.log('[비디오 디버그] 메타데이터 로드 완료')}
                    onCanPlay={() => console.log('[비디오 디버그] 재생 가능 상태 도달')}
                    onError={(e) => {
                      console.error('[비디오 디버그] 에러 발생!', e.target.error);
                      if (e.target.error) {
                        console.error('에러 코드:', e.target.error.code, '에러 메시지:', e.target.error.message);
                      }
                    }}
                  />
                ) : (
                  // 시스템 알림(순찰·복귀·배터리)은 보여줄 영상이 없다.
                  // 예전에는 Unsplash 스톡 사진을 외부에서 받아왔으나, 이 드론의 사진도 아니고
                  // 인터넷이 끊기면 깨졌다. 상태를 그대로 말해 주는 아이콘으로 바꿨다.
                  <div className={`w-full h-full flex items-center justify-center ${
                    alert.tone === 'green' ? 'bg-green-50 text-green-600'
                      : alert.tone === 'blue' ? 'bg-blue-50 text-blue-600'
                      : alert.tone === 'amber' ? 'bg-amber-50 text-amber-600'
                      : 'bg-gray-100 text-gray-500'
                  }`}>
                    <span className="material-symbols-outlined text-3xl">{alert.icon || 'notifications'}</span>
                  </div>
                )}
              </div>
              <div>
                <p className="text-sm font-bold text-[#0b1c30] mb-1">{alert.title}</p>
                <p className="text-[11px] text-[#424754] leading-relaxed line-clamp-2">{alert.desc}</p>
                <div className="mt-2 flex items-center gap-1 text-[#0058be]">
                  <span className="material-symbols-outlined text-sm">location_on</span>
                  <span className="text-[10px] font-bold">{alert.source}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
