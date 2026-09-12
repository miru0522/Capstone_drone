import { useState } from 'react';
import toast from 'react-hot-toast';
import { getApiBaseUrl } from '../../config';
import { approveTTS } from '../../services/api';
import ConfirmDialog from '../common/ConfirmDialog';
import { fmtDateTime, isPastMediaRetention } from '../../utils/time';
import { DetailHeader, DroneChip, SectionLabel, StatusPill } from './HistoryParts';
import { classTone, isHandled, statusLabel } from '../../utils/incidentStatus';

/**
 * 이상 이벤트 상세 — 영상 + AI 분석 결과.
 * 사이드탭 모달에 있던 것을 HISTORY 패널로 옮기면서 재사용 가능하게 분리했다.
 */
export default function IncidentDetail({ log, onBack }) {
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);
  // 현장에 소리가 나가는 조작이라 확인을 받는다.
  const [broadcastOpen, setBroadcastOpen] = useState(false);

  const runBroadcast = async () => {
    setApproving(true);
    try {
      await approveTTS(log.eventId);
      setApproved(true);
      setBroadcastOpen(false);
    } catch (err) {
      toast.error(err.userMessage ?? '승인에 실패했습니다. 잠시 후 다시 시도해주세요.');
    } finally {
      setApproving(false);
    }
  };

  if (!log) return null;

  const tone = classTone(log.secondClassificationResult);
  // 서버 기본값이 PENDING 이라 "값이 있음"이 아니라 승인·송출 여부로 본다
  const handled = isHandled(log.adminApprovalStatus);

  return (
    // 배치는 화면 폭이 아니라 이 상세가 받은 자리의 폭으로 정한다(@container) — 사이드바·경보 패널이
    // 열려 있으면 화면이 넓어도 자리가 좁다. 좁으면 영상을 위에 전체 폭으로, 분석을 아래로 쌓는다.
    // 전에는 분석 패널이 380px 고정이라, 좁은 자리에서 영상만 142px 까지 줄어
    // 브라우저가 재생바·버튼을 쓸 수 없게 줄여 버렸다(2026-09-11 헤드리스 Chrome 실측).
    <div className="@container h-full">
    <div className="flex flex-col gap-4 min-h-full @3xl:h-full @3xl:min-h-[520px]">
      <DetailHeader
        onBack={onBack}
        title={
          <>
            Incident #{log.eventId || log.id}
            <span className={`px-2 py-0.5 rounded-md border text-xs font-bold ${tone.badge}`}>
              {log.secondClassificationResult || 'UNKNOWN'}
            </span>
          </>
        }
        meta={<>{fmtDateTime(log.timestamp)} · <DroneChip id={log.droneId} /></>}
        right={<StatusPill status={approved ? 'APPROVED' : log.adminApprovalStatus} />}
      />

      <div className="flex flex-col @3xl:flex-row @3xl:flex-1 @3xl:min-h-0 bg-white rounded-xl border border-[#c2c6d6]/70 shadow-sm overflow-hidden">
        {/* 왼쪽 — 영상 */}
        <div className="bg-black p-4 flex items-center justify-center aspect-video @3xl:aspect-auto @3xl:flex-1 @3xl:min-w-0">
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
              <p className="text-sm">
                {isPastMediaRetention(log.timestamp)
                  ? '보존 기간(1년)이 지나 영상이 삭제되었습니다.'
                  : '저장된 영상이 없습니다.'}
              </p>
            </div>
          )}
        </div>

        {/* 오른쪽 — 분석 내용 */}
        <div className="border-t @3xl:border-t-0 @3xl:border-l border-[#c2c6d6]/70 bg-[#f8f9ff] @3xl:w-[380px] @3xl:overflow-y-auto shrink-0">
          <div className="p-5 space-y-5">
            <div>
              <SectionLabel icon="visibility">VLM 상황 분석</SectionLabel>
              <div className="bg-white border border-[#c2c6d6] rounded-xl p-4 text-sm text-[#0b1c30] leading-relaxed shadow-sm">
                {log.vlmSituationDesc || '분석 내용이 없습니다.'}
              </div>
            </div>

            <div>
              <SectionLabel icon="campaign">방송 대본 (TTS)</SectionLabel>
              <div className="bg-[#dae2fd] border border-[#a8b8e0] rounded-xl p-4 text-sm font-semibold text-[#0058be] leading-relaxed shadow-sm">
                "{log.vlmTtsCandidate || '방송 대본이 없습니다.'}"
              </div>

              {/* 알림창에서 X로 닫았거나 새로고침으로 놓친 건을 여기서 이어서 조치한다.
                  이미 승인·송출된 건은 버튼 대신 상태만 보여 준다. */}
              {handled ? (
                <p className="mt-2 text-xs font-semibold text-[#727785] flex items-center gap-1">
                  <span className="material-symbols-outlined text-[16px] text-green-600">check_circle</span>
                  {log.adminApprovalStatus === 'BROADCAST_COMPLETED' ? '현장 방송까지 완료된 건입니다.' : '승인 완료된 건입니다.'}
                </p>
              ) : (
                <button
                  type="button"
                  disabled={approving || approved || !log.vlmTtsCandidate}
                  onClick={() => setBroadcastOpen(true)}
                  className="mt-3 w-full py-2.5 rounded-xl text-sm font-bold text-white transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed bg-[#0058be] hover:bg-[#00479b] cursor-pointer"
                >
                  {approved ? '승인 완료 — 방송이 송출됩니다'
                    : approving ? '승인 중…'
                    : !log.vlmTtsCandidate ? '방송 대본이 없어 승인할 수 없습니다'
                    : 'TTS 경고 방송 승인'}
                </button>
              )}
            </div>

            <div className="pt-4 border-t border-[#c2c6d6] space-y-3">
              {/* 1차는 드론의 VadCLIP, 2차는 서버의 VideoMAE. 예전에는 1차만 그렸는데
                  그 값이 전달되지 않아 늘 0%였고, 값이 있는 2차는 화면에 없었다. */}
              {[
                ['1차 점수 (VAD)', log.firstAnomalyScore],
                ['2차 점수 (VideoMAE)', log.secondAnomalyScore],
              ].map(([label, score]) => (
                <div key={label} className="flex justify-between items-center text-sm">
                  <span className="text-[#727785] font-medium">{label}</span>
                  <span className="font-mono tabular-nums bg-white border border-[#c2c6d6] text-[#0b1c30] px-2 py-0.5 rounded font-bold">
                    {typeof score === 'number' ? (score * 100).toFixed(1) + '%' : '측정값 없음'}
                  </span>
                </div>
              ))}
              <div className="flex justify-between items-center text-sm">
                <span className="text-[#727785] font-medium">조치 상태</span>
                <span className="font-bold text-[#0b1c30]">{statusLabel(approved ? 'APPROVED' : log.adminApprovalStatus)}</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-[#727785] font-medium">드론</span>
                <DroneChip id={log.droneId} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {broadcastOpen && (
        <ConfirmDialog
          tone="danger"
          icon="campaign"
          title="경고 방송 송출"
          subtitle={log.droneId}
          confirmLabel="송출"
          isBusy={approving}
          onConfirm={runBroadcast}
          onClose={() => setBroadcastOpen(false)}
        >
          <p>
            이 대본으로 <span className="font-bold">현장에 실제 경고 방송</span>이 나갑니다.
            <span className="text-red-500 font-bold bg-red-50 px-1 mt-1 inline-block">현장에 있는 사람에게 들립니다.</span>
          </p>
          {log.vlmTtsCandidate && (
            <p className="text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 mt-3 leading-relaxed">
              {log.vlmTtsCandidate}
            </p>
          )}
        </ConfirmDialog>
      )}
    </div>
    </div>
  );
}
