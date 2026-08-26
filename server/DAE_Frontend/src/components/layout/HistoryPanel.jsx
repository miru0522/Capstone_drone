import React, { useState, useEffect } from 'react';
import useUserStore from '../../store/useUserStore';
import useDroneStore from '../../store/useDroneStore';
import api from '../../services/api';
import IncidentDetail from '../history/IncidentDetail';
import FlightDetail from '../history/FlightDetail';

// 지도 (상세 뷰는 FlightDetail이 그리지만 마커 아이콘 설정은 여기서 한 번 해둔다)
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// 기본 마커 아이콘 설정 (웹팩/Vite 이슈 방지)
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

export default function HistoryPanel() {
  const { isHistoryOpen, closeHistory } = useUserStore((state) => state);
  const [activeTab, setActiveTab] = useState('flight'); // 'flight' | 'incident'
  // 드론 목록은 등록된 것에서 가져온다. 새로 등록하면 자동으로 늘어난다.
  const drones = useDroneStore((state) => state.drones);
  const [droneId, setDroneId] = useState('');
  const [selectedDate, setSelectedDate] = useState(''); // Date picker state
  const [sessions, setSessions] = useState([]);          // 비행 목록
  const [selectedFlight, setSelectedFlight] = useState(null);
  const [flightPoints, setFlightPoints] = useState([]);  // 선택한 비행의 궤적/차트 데이터
  const [incidentLogs, setIncidentLogs] = useState([]);
  const [selectedLog, setSelectedLog] = useState(null);   // 선택 시 상세 뷰로 전환
  const [loading, setLoading] = useState(false);

  // 비행 목록. 세션 경계는 서버가 원시 데이터로 판정한다(프론트에서 나누면 안 된다 — 조회 API가 5m 필터를 건다).
  const fetchSessions = async () => {
    if (!droneId) return;
    setLoading(true);
    try {
      const dateQuery = selectedDate ? `&date=${selectedDate}` : '';
      const response = await api.get(`/drones/${droneId}/flights?hours=24${dateQuery}`);
      setSessions(response.data || []);
    } catch (error) {
      console.error("비행 목록 조회 실패:", error);
      setSessions([]);
    } finally {
      setLoading(false);
    }
  };

  // 선택한 비행의 구간만 조회한다
  const openFlight = async (session) => {
    setSelectedFlight(session);
    setFlightPoints([]);
    setLoading(true);
    try {
      const params = new URLSearchParams({ from: session.startedAt, to: session.endedAt });
      const response = await api.get(`/drones/${droneId}/telemetry?${params}`);
      setFlightPoints(response.data || []);
    } catch (error) {
      console.error("비행 상세 조회 실패:", error);
    } finally {
      setLoading(false);
    }
  };

  // 이상 이벤트 이력 조회
  const fetchIncidentLogs = async () => {
    setLoading(true);
    try {
      const response = await api.get(`/events`);
      // 최신순 정렬 (ID 또는 시간 역순)
      const sorted = (response.data || []).sort((a, b) => {
        return (b.eventId || b.id || 0) - (a.eventId || a.id || 0);
      });
      setIncidentLogs(sorted);
    } catch (error) {
      console.error("이벤트 이력 조회 실패:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!droneId && drones.length > 0) setDroneId(drones[0].id);
  }, [drones, droneId]);

  useEffect(() => {
    if (isHistoryOpen) {
      // 탭 이동·패널 재오픈은 물론 드론·날짜를 바꿔도 목록부터 보여준다.
      // (해제하지 않으면 다른 날 데이터 위에 이전 선택이 남는다)
      setSelectedLog(null);
      setSelectedFlight(null);
      setFlightPoints([]);
      if (activeTab === 'flight') {
        fetchSessions();
      } else if (activeTab === 'incident') {
        fetchIncidentLogs();
      }
    }
  }, [isHistoryOpen, activeTab, droneId, selectedDate]);

  if (!isHistoryOpen) return null;

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#f8f9ff]/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white w-[90%] max-w-[1200px] h-[85vh] rounded-2xl shadow-xl flex flex-col overflow-hidden border border-gray-200">

        {/* 헤더 */}
        <div className="flex items-center justify-between px-8 py-5 border-b border-gray-100 bg-gray-50/50">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-blue-600 text-[28px]">history</span>
            <h2 className="text-2xl font-bold text-gray-800 tracking-tight">System History</h2>
          </div>
          <button
            onClick={closeHistory}
            className="p-2 hover:bg-gray-200 rounded-full transition-colors text-gray-500"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* 탭 메뉴 */}
        <div className="flex border-b border-gray-200 px-8">
          <button
            onClick={() => setActiveTab('flight')}
            className={`py-4 px-6 font-medium text-sm border-b-2 transition-colors ${
              activeTab === 'flight' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Flight History
          </button>
          <button
            onClick={() => setActiveTab('incident')}
            className={`py-4 px-6 font-medium text-sm border-b-2 transition-colors ${
              activeTab === 'incident' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Incident Logs
          </button>
        </div>

        {/* 콘텐츠 영역 */}
        <div className="flex-1 overflow-y-auto p-8 bg-gray-50/30">

          {activeTab === 'flight' && (
            <div className="flex flex-col gap-6 h-full">
              {/* 컨트롤 패널 */}
              <div className="flex items-center justify-between bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
                <div className="flex items-center gap-4">
                  <span className="text-sm font-semibold text-gray-600">Drone Target</span>
                  <select
                    value={droneId}
                    onChange={(e) => setDroneId(e.target.value)}
                    className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {drones.length === 0 && <option value="">등록된 드론 없음</option>}
                    {drones.map(d => (
                      <option key={d.id} value={d.id}>
                        {d.id}{d.name ? ` (${d.name})` : ''}
                      </option>
                    ))}
                  </select>

                  <span className="text-sm font-semibold text-gray-600 ml-2">Date</span>
                  <input
                    type="date"
                    value={selectedDate}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />

                  {loading && <span className="text-sm text-gray-400">데이터 불러오는 중...</span>}
                </div>
                <button
                  onClick={fetchSessions}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-[18px]">search</span>
                  조회하기
                </button>
              </div>

              {selectedFlight ? (
                <FlightDetail
                  session={selectedFlight}
                  points={flightPoints}
                  loading={loading}
                  onBack={() => { setSelectedFlight(null); setFlightPoints([]); }}
                />
              ) : sessions.length > 0 ? (
                <ul className="flex flex-col gap-2">
                  {sessions.map((s, i) => {
                    const start = new Date(s.startedAt);
                    const end = new Date(s.endedAt);
                    const mins = Math.max(1, Math.round((end - start) / 60000));
                    return (
                      <li key={i}>
                        <button
                          onClick={() => openFlight(s)}
                          className="w-full flex items-center gap-4 p-4 bg-white border border-gray-200 rounded-xl shadow-sm hover:bg-blue-50/50 hover:border-blue-200 transition-colors text-left"
                        >
                          <span className="material-symbols-outlined text-blue-600">drone</span>
                          <div className="min-w-0 flex-1">
                            <p className="font-bold text-sm text-gray-800">
                              {start.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                              {' ~ '}
                              {s.inProgress
                                ? <span className="text-blue-600">비행 중</span>
                                : end.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                              <span className="ml-2 font-normal text-gray-500">{mins}분</span>
                            </p>
                            <p className="text-xs text-gray-500">
                              {start.toLocaleDateString('ko-KR')} · {s.pointCount}개 지점
                              {' · '}{(s.distanceM / 1000).toFixed(2)}km
                              {s.maxAltM != null && ` · 최고 ${s.maxAltM.toFixed(0)}m`}
                            </p>
                          </div>
                          {s.batteryStart != null && s.batteryEnd != null && (
                            <span className="text-xs font-mono text-gray-600 bg-gray-100 px-2 py-1 rounded shrink-0">
                              {s.batteryStart.toFixed(0)}% → {s.batteryEnd.toFixed(0)}%
                            </span>
                          )}
                          <span className="material-symbols-outlined text-gray-400 shrink-0">chevron_right</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-400 gap-2">
                  <span className="material-symbols-outlined text-5xl">drone</span>
                  <p className="text-sm">
                    {loading ? '불러오는 중...'
                      : drones.length === 0 ? '등록된 드론이 없습니다.'
                      : '이 기간에 비행 기록이 없습니다.'}
                  </p>
                  {!loading && drones.length > 0 && (
                    <p className="text-xs text-gray-400">
                      2026-08-14 이전 데이터는 상태 정보가 없어 조회되지 않습니다.
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {activeTab === 'incident' && (
            selectedLog ? (
              /* 상세 뷰 — 영상 + AI 분석 (사이드탭 모달에서 이전) */
              <IncidentDetail log={selectedLog} onBack={() => setSelectedLog(null)} />
            ) : (
              <div className="flex flex-col gap-6 h-full">
                <div className="flex items-center justify-between bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
                  <div className="flex items-center gap-4">
                    <span className="text-sm font-semibold text-gray-600">Event Logs</span>
                    <span className="text-sm text-gray-400">행을 클릭하면 영상과 AI 분석 결과를 볼 수 있습니다.</span>
                    {loading && <span className="text-sm text-gray-400">데이터 불러오는 중...</span>}
                  </div>
                  <button
                    onClick={fetchIncidentLogs}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                  >
                    <span className="material-symbols-outlined text-[18px]">refresh</span>
                    최신 조회
                  </button>
                </div>

                <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex-1 flex flex-col">
                  <div className="overflow-x-auto flex-1">
                    <table className="w-full text-left border-collapse">
                      <thead className="bg-gray-50 border-b border-gray-200">
                        <tr>
                          <th className="py-3 px-4 font-semibold text-gray-600 text-sm whitespace-nowrap text-center">ID</th>
                          <th className="py-3 px-4 font-semibold text-gray-600 text-sm whitespace-nowrap">발생 시간</th>
                          <th className="py-3 px-4 font-semibold text-gray-600 text-sm whitespace-nowrap">분류/라벨</th>
                          <th className="py-3 px-4 font-semibold text-gray-600 text-sm whitespace-nowrap">상세 설명</th>
                          <th className="py-3 px-4 font-semibold text-gray-600 text-sm whitespace-nowrap text-center">조치 상태</th>
                          <th className="py-3 px-4 font-semibold text-gray-600 text-sm whitespace-nowrap text-center">미디어</th>
                        </tr>
                      </thead>
                      <tbody>
                        {incidentLogs.length > 0 ? incidentLogs.map((log) => (
                          <tr
                            key={log.eventId || log.id}
                            onClick={() => setSelectedLog(log)}
                            className="border-b border-gray-100 hover:bg-blue-50 cursor-pointer transition-colors"
                          >
                            <td className="py-3 px-4 text-sm text-gray-500 text-center">#{log.eventId || log.id}</td>
                            <td className="py-3 px-4 text-sm text-gray-700">
                              {log.timestamp ? new Date(log.timestamp).toLocaleString('ko-KR') : '-'}
                            </td>
                            <td className="py-3 px-4">
                              <span className="bg-orange-100 text-orange-700 text-xs font-bold px-2 py-1 rounded-md">
                                {log.secondClassificationResult || log.type || 'Unknown'}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-sm text-gray-600 max-w-xs truncate" title={log.vlmSituationDesc || log.desc}>
                              {log.vlmSituationDesc || log.desc || '-'}
                            </td>
                            <td className="py-3 px-4 text-sm text-center">
                              {log.adminApprovalStatus === 'BROADCAST_COMPLETED' ? (
                                <span className="text-green-600 font-semibold flex items-center justify-center gap-1">
                                  <span className="material-symbols-outlined text-[16px]">campaign</span>
                                  송출 완료
                                </span>
                              ) : log.adminApprovalStatus === 'APPROVED' ? (
                                <span className="text-blue-600 font-semibold flex items-center justify-center gap-1">
                                  <span className="material-symbols-outlined text-[16px]">check_circle</span>
                                  승인됨
                                </span>
                              ) : (
                                <span className="text-gray-400 font-medium">대기중</span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-center">
                              {log.videoClipPath ? (
                                <span className="material-symbols-outlined text-[20px] text-blue-500">videocam</span>
                              ) : (
                                <span className="text-gray-300">-</span>
                              )}
                            </td>
                          </tr>
                        )) : (
                          <tr>
                            <td colSpan="6" className="py-10 text-center text-gray-400 text-sm">
                              조회된 사고 이력이 없습니다.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )
          )}

        </div>
      </div>
    </div>
  );
}
