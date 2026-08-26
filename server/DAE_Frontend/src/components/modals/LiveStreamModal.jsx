import React, { useEffect, useState } from 'react';
import useDroneStore from '../../store/useDroneStore';
import { startStream, stopStream } from '../../services/api';

/**
 * 실시간 영상 (2026-08-22 드론팀 합의).
 *
 * 드론은 상시 송출하지 않는다. 열 때 REQUEST_STREAM을 보내 시작시키고,
 * 닫을 때 STOP_STREAM으로 멈춘다 — 아무도 안 보는 영상을 계속 올리면
 * 배터리와 셀룰러 요금을 태우기 때문이다.
 *
 * 화면은 MJPEG를 <img> 하나로 받는다. 별도 라이브러리도 코덱도 필요 없다.
 * 인증은 쿠키로 실려 가므로 헤더를 따로 붙이지 않아도 된다.
 */
export default function LiveStreamModal() {
  const { isOpen, droneId } = useDroneStore((state) => state.liveStreamModal);
  const closeLiveStream = useDroneStore((state) => state.closeLiveStream);

  const [phase, setPhase] = useState('starting');   // starting | live | error
  const [src, setSrc] = useState(null);

  useEffect(() => {
    if (!isOpen || !droneId) return;
    let cancelled = false;

    setPhase('starting');
    setSrc(null);

    startStream(droneId)
      .then(() => {
        if (cancelled) return;
        // 세션이 열린 뒤에 <img>를 붙인다. 먼저 붙이면 서버가 404를 준다.
        // 캐시 방지용 쿼리 — 같은 URL을 재사용하면 브라우저가 옛 스트림을 되쓴다.
        setSrc(`/drones/${droneId}/stream?t=${Date.now()}`);
        setPhase('live');
      })
      .catch((e) => {
        console.error('스트림 시작 실패', e);
        if (!cancelled) setPhase('error');
      });

    return () => {
      cancelled = true;
      // 화면이 사라지는 길에 반드시 멈춘다. 서버의 410은 안전망이지 정상 경로가 아니다.
      stopStream(droneId);
    };
  }, [isOpen, droneId]);

  if (!isOpen) return null;

  return (
    <div className="absolute inset-0 flex items-center justify-center z-[120] bg-black/50 backdrop-blur-[2px]">
      <div className="bg-white w-full max-w-2xl rounded-2xl shadow-2xl p-5 relative animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-sm flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-red-500">videocam</span>
            실시간 영상
            <span className="font-mono text-xs text-gray-500">{droneId}</span>
          </h3>
          <button
            type="button"
            onClick={closeLiveStream}
            aria-label="닫기"
            className="text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="bg-black rounded-xl overflow-hidden aspect-video flex items-center justify-center">
          {phase === 'starting' && (
            <p className="text-gray-400 text-xs">드론에 영상 전송을 요청하는 중…</p>
          )}
          {phase === 'error' && (
            <p className="text-red-400 text-xs">영상을 시작하지 못했습니다. 드론 연결을 확인해 주세요.</p>
          )}
          {phase === 'live' && src && (
            <img
              src={src}
              alt={`${droneId} 실시간 영상`}
              className="w-full h-full object-contain"
              onError={() => setPhase('error')}
            />
          )}
        </div>

        <p className="text-[11px] text-gray-400 mt-2 text-center">
          640×480 · 5fps · 이 창을 닫으면 드론의 영상 전송이 멈춥니다
        </p>
      </div>
    </div>
  );
}
