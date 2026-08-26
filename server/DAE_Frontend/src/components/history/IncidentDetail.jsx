import { useState } from 'react';
import { getApiBaseUrl } from '../../config';
import { approveTTS } from '../../services/api';

/** 분류 결과에 따른 배지 색. 모르는 값은 노란색으로 떨어뜨린다. */
const classCls = (result) => {
  if (result === 'ASSAULT' || result === 'CRITICAL') return 'bg-red-100 text-red-700 border-red-200';
  if (result === 'FIGHT') return 'bg-orange-100 text-orange-700 border-orange-200';
  return 'bg-yellow-100 text-yellow-700 border-yellow-200';
};

/**
 * 이상 이벤트 상세 — 영상 + AI 분석 결과.
 * 사이드탭 모달에 있던 것을 HISTORY 패널로 옮기면서 재사용 가능하게 분리했다.
 */
export default function IncidentDetail({ log, onBack }) {
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);

  if (!log) return null;

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {/* 헤더 */}
      <div className="flex items-center gap-3 p-4 bg-[#f8f9ff] border-b border-gray-200 shrink-0">
        <button
          onClick={onBack}
          className="p-2 bg-white border border-[#c2c6d6] text-[#424754] hover:bg-[#e5eeff] rounded-lg transition-colors flex items-center justify-center"
          title="목록으로"
        >
          <span className="material-symbols-outlined text-[20px]">arrow_back</span>
        </button>
        <div>
          <h3 className="text-lg font-bold text-[#0b1c30]">Incident #{log.eventId || log.id}</h3>
          <p className="text-xs text-[#727785]">
            {log.timestamp ? new Date(log.timestamp).toLocaleString('ko-KR') : '시각 정보 없음'}
          </p>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* 왼쪽 — 영상 */}
        <div className="flex-1 bg-black p-4 flex items-center justify-center">
          {log.videoClipPath ? (
            <video
              controls
              className="max-h-full max-w-full rounded-lg border border-gray-700 shadow-lg"
              /* 상대경로로 저장되므로 베이스 URL을 붙여야 재생된다 */
              src={`${getApiBaseUrl()}${log.videoClipPath}`}
            />
          ) : (
            <div className="flex flex-col items-center text-gray-500 gap-3">
              <span className="material-symbols-outlined text-5xl">videocam_off</span>
              <p className="text-sm">저장된 영상이 없습니다.</p>
            </div>
          )}
        </div>

        {/* 오른쪽 — 분석 내용 */}
        <div className="w-[380px] border-l border-gray-200 bg-[#f8f9ff] overflow-y-auto shrink-0">
          <div className="p-5 space-y-5">
            <div>
              <h4 className="text-xs font-bold text-[#727785] uppercase tracking-wider mb-2">AI Classification</h4>
              <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border font-bold ${classCls(log.secondClassificationResult)}`}>
                <span className="material-symbols-outlined text-[18px]">
                  {log.secondClassificationResult === 'ASSAULT' ? 'warning' : 'info'}
                </span>
                {log.secondClassificationResult || 'UNKNOWN'}
              </div>
            </div>

            <div>
              <h4 className="text-xs font-bold text-[#727785] uppercase tracking-wider mb-2 flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">visibility</span>
                VLM 상황 분석
              </h4>
              <div className="bg-white border border-[#c2c6d6] rounded-xl p-4 text-sm text-[#0b1c30] leading-relaxed shadow-sm">
                {log.vlmSituationDesc || '분석 내용이 없습니다.'}
              </div>
            </div>

            <div>
              <h4 className="text-xs font-bold text-[#727785] uppercase tracking-wider mb-2 flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">campaign</span>
                방송 대본 (TTS)
              </h4>
              <div className="bg-[#dae2fd] border border-[#a8b8e0] rounded-xl p-4 text-sm font-semibold text-[#0058be] leading-relaxed shadow-sm">
                "{log.vlmTtsCandidate || '방송 대본이 없습니다.'}"
              </div>

              {/* 알림창에서 X로 닫았거나 새로고침으로 놓친 건을 여기서 이어서 조치한다.
                  이미 승인·송출된 건은 버튼 대신 상태만 보여 준다. */}
              {log.adminApprovalStatus ? (
                <p className="mt-2 text-xs font-semibold text-[#727785] flex items-center gap-1">
                  <span className="material-symbols-outlined text-[16px] text-green-600">check_circle</span>
                  {log.adminApprovalStatus === 'BROADCAST_COMPLETED' ? '현장 방송까지 완료된 건입니다.' : '승인 완료된 건입니다.'}
                </p>
              ) : (
                <button
                  type="button"
                  disabled={approving || approved || !log.vlmTtsCandidate}
                  onClick={async () => {
                    if (!window.confirm('이 대본으로 현장에 경고 방송을 송출합니다. 진행할까요?')) return;
                    setApproving(true);
                    try {
                      await approveTTS(log.eventId);
                      setApproved(true);
                    } catch (e) {
                      alert('승인에 실패했습니다. 잠시 후 다시 시도해주세요.');
                    } finally {
                      setApproving(false);
                    }
                  }}
                  className="mt-3 w-full py-2.5 rounded-xl text-sm font-bold text-white transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed bg-[#0058be] hover:bg-[#00479b]"
                >
                  {approved ? '승인 완료 — 방송이 송출됩니다'
                    : approving ? '승인 중…'
                    : !log.vlmTtsCandidate ? '방송 대본이 없어 승인할 수 없습니다'
                    : 'TTS 경고 방송 승인'}
                </button>
              )}
            </div>

            <div className="pt-4 border-t border-[#c2c6d6] space-y-3">
              <div className="flex justify-between items-center text-sm">
                <span className="text-[#727785] font-medium">이상 점수</span>
                <span className="font-mono bg-gray-200 text-gray-800 px-2 py-0.5 rounded font-bold">
                  {typeof log.firstAnomalyScore === 'number'
                    ? (log.firstAnomalyScore * 100).toFixed(1) + '%'
                    : '-'}
                </span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-[#727785] font-medium">조치 상태</span>
                <span className="font-bold text-[#0b1c30]">{log.adminApprovalStatus || '-'}</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-[#727785] font-medium">드론</span>
                <span className="font-bold text-[#0b1c30]">
                  {log.droneId || '-'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
