import React, { useState, useEffect, useRef, useLayoutEffect } from 'react';
import useUserStore from '../../store/useUserStore';
import useDroneStore from '../../store/useDroneStore';
import api, { getCommandLogs } from '../../services/api';
import toast from 'react-hot-toast';
import { COMMAND_LABEL } from '../../utils/droneStatus';
import IncidentDetail from '../history/IncidentDetail';
import FlightDetail from '../history/FlightDetail';
import { DroneChip, EmptyState, StatusPill } from '../history/HistoryParts';
import { classTone, isHandled } from '../../utils/incidentStatus';

// 지도 (상세 뷰는 FlightDetail이 그리지만 마커 아이콘 설정은 여기서 한 번 해둔다)
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { parseServerTime, rangeToServer, DEFAULT_RANGE, fmtDateTime, fmtClock, fmtDayHeader } from '../../utils/time';
import DateRangePicker from '../common/DateRangePicker';
import DroneMultiSelect from '../common/DroneMultiSelect';

// 기본 마커 아이콘 설정 (웹팩/Vite 이슈 방지)
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const TABS = [
  ['flight', 'Flight History', 'drone'],
  ['incident', 'Incident Logs', 'warning'],
  ['command', 'Command Logs', 'terminal'],
];

// 표 머리·행 — 사고와 조작이 같은 모양을 쓴다. 머리는 목록을 내려도 위에 붙어 있다.
const TH = 'sticky top-0 z-10 bg-[#f8f9ff] px-4 py-2.5 text-[11px] font-bold uppercase tracking-wider text-[#727785] border-b border-[#c2c6d6]/70';
// 행 높이를 고정한다 — 칸 내용(아이콘·배지)에 따라 사고와 조작 표의 높이가 달랐다.
// 사고 표의 원래 높이 56px(헤드리스 Chrome 실측)에 조작 표를 맞춘다. 사고 표는 줄이지 않는다.
const ROW = 'h-14 border-b border-gray-100 last:border-0 hover:bg-[#e5eeff]/50 transition-colors';

/**
 * 명령 성격별 색 — 멈추는 명령일수록 눈에 띄게.
 * 사고 표의 분류 색과 같은 방식(왼쪽 띠 + 배지)이다. 두 기록 표는 모양이 같아야 한다.
 */
const actionTone = (action) => {
  if (action === 'EMERGENCY_STOP') return { badge: 'bg-red-50 text-red-700 border-red-200', stripe: 'bg-red-500' };
  if (action === 'LAND' || action === 'RETURN_TO_STATION' || action === 'PAUSE_PATROL' || action === 'CANCEL_PATROL') {
    return { badge: 'bg-amber-50 text-amber-700 border-amber-200', stripe: 'bg-amber-400' };
  }
  return { badge: 'bg-[#e5eeff] text-[#0058be] border-[#c9d8f5]', stripe: 'bg-[#0058be]' };
};

/** 비행 1회의 배터리 — 시작에서 끝까지 쓴 만큼을 막대로. 40%는 자율 복귀 기준이다. */
function BatteryBar({ start, end }) {
  if (start == null || end == null) return <div className="w-28 shrink-0" />;
  const clamp = (v) => Math.max(0, Math.min(100, v));
  const s = clamp(start);
  const e = clamp(end);
  const tone = e <= 40 ? 'bg-red-500' : e <= 60 ? 'bg-amber-500' : 'bg-green-500';
  return (
    <div className="w-28 shrink-0" title={`배터리 ${s.toFixed(0)}% → ${e.toFixed(0)}%`}>
      <div className="flex justify-between text-[11px] font-mono tabular-nums text-[#424754] mb-1">
        <span>{s.toFixed(0)}%</span>
        <span>→ {e.toFixed(0)}%</span>
      </div>
      <div className="relative h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div className="absolute inset-y-0 left-0 bg-gray-300" style={{ width: `${s}%` }} />
        <div className={`absolute inset-y-0 left-0 ${tone}`} style={{ width: `${e}%` }} />
      </div>
    </div>
  );
}

export default function HistoryPanel() {
  const { isHistoryOpen, closeHistory } = useUserStore((state) => state);
  const [activeTab, setActiveTab] = useState('flight'); // 'flight' | 'incident' | 'command'
  // 드론 목록은 등록된 것에서 가져온다. 새로 등록하면 자동으로 늘어난다.
  const drones = useDroneStore((state) => state.drones);
  // 조회할 드론. null 이면 전체 — 나중에 등록한 드론도 저절로 들어간다(2026-09-11 결정).
  // 세 탭이 함께 쓴다.
  const [selectedDrones, setSelectedDrones] = useState(null);
  // 드론 목록은 텔레메트리가 올 때마다(1초) 새 배열이 된다. 의존성에는 id 문자열을 쓴다.
  const droneIdsKey = drones.map((d) => d.id).join(',');
  const targetIds = selectedDrones ?? drones.map((d) => d.id);
  const noneSelected = selectedDrones !== null && selectedDrones.length === 0;
  /** 서버에 보낼 드론 조건. 전체면 보내지 않는다 — 드론이 기록되지 않은 사고도 보이도록. */
  const droneFilter = selectedDrones ?? [];

  // 필터 줄은 고정하고 목록만 자기 안에서 스크롤한다(스크롤바가 생겨도 필터 줄이 밀리지 않게).
  // 상세에서 돌아오면 목록을 보던 자리로 되돌린다.
  const scrollRef = useRef(null);
  const savedScroll = useRef(0);
  const rememberScroll = () => {
    savedScroll.current = scrollRef.current?.scrollTop ?? 0;
  };
  // 세 탭이 같은 기간을 쓴다 — 탭을 옮겨도 보던 기간이 유지된다(2026-09-10 결정)
  const [range, setRange] = useState(DEFAULT_RANGE);
  const [sessions, setSessions] = useState([]);          // 비행 목록
  const [selectedFlight, setSelectedFlight] = useState(null);
  const [flightPoints, setFlightPoints] = useState([]);  // 선택한 비행의 궤적/차트 데이터
  const [incidentLogs, setIncidentLogs] = useState([]);
  const [selectedLog, setSelectedLog] = useState(null);   // 선택 시 상세 뷰로 전환
  const [commandLogs, setCommandLogs] = useState([]);     // 조작 이력
  const [loading, setLoading] = useState(false);

  // 비행 목록. 세션 경계는 서버가 원시 데이터로 판정한다(프론트에서 나누면 안 된다 — 조회 API가 5m 필터를 건다).
  const fetchSessions = async () => {
    if (targetIds.length === 0) {
      setSessions([]);
      return;
    }
    setLoading(true);
    try {
      const params = rangeToServer(range);
      // 비행 목록 API는 드론 하나씩이다. 고른 드론마다 조회해 합친다.
      // 응답에 드론 id가 없어 여기서 붙인다 — 상세 조회가 그 드론으로 가야 한다.
      // 한 대가 실패해도 나머지는 보여준다.
      const lists = await Promise.all(targetIds.map((id) =>
        api.get(`/drones/${id}/flights`, { params })
          .then((r) => (r.data || []).map((s) => ({ ...s, droneId: id })))
          .catch((error) => {
            console.error(`비행 목록 조회 실패 (${id}):`, error);
            return [];
          })));
      setSessions(lists.flat().sort((a, b) => parseServerTime(b.startedAt) - parseServerTime(a.startedAt)));
    } finally {
      setLoading(false);
    }
  };

  // 선택한 비행의 구간만 조회한다
  const openFlight = async (session) => {
    rememberScroll();
    setSelectedFlight(session);
    setFlightPoints([]);
    setLoading(true);
    try {
      const params = new URLSearchParams({ from: session.startedAt, to: session.endedAt });
      const response = await api.get(`/drones/${session.droneId}/telemetry?${params}`);
      setFlightPoints(response.data || []);
    } catch (error) {
      console.error("비행 상세 조회 실패:", error);
    } finally {
      setLoading(false);
    }
  };

  // 이상 이벤트 이력 조회
  const fetchIncidentLogs = async () => {
    if (noneSelected) {
      setIncidentLogs([]);
      return;
    }
    setLoading(true);
    try {
      // 드론 여러 대는 ?droneId=A&droneId=B — axios 배열 형식(droneId[]=)은 서버가 못 받는다
      const params = new URLSearchParams(rangeToServer(range));
      droneFilter.forEach((id) => params.append('droneId', id));
      const response = await api.get('/events', { params });
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
    if (isHistoryOpen) {
      // 탭 이동·패널 재오픈은 물론 드론·날짜를 바꿔도 목록부터 보여준다.
      // (해제하지 않으면 다른 날 데이터 위에 이전 선택이 남는다)
      // 목록 내용이 바뀌므로 보던 자리도 버린다
      savedScroll.current = 0;
      if (scrollRef.current) scrollRef.current.scrollTop = 0;
      setSelectedLog(null);
      setSelectedFlight(null);
      setFlightPoints([]);
      if (activeTab === 'flight') {
        fetchSessions();
      } else if (activeTab === 'incident') {
        fetchIncidentLogs();
      } else if (activeTab === 'command') {
        fetchCommandLogs();
      }
    }
  }, [isHistoryOpen, activeTab, selectedDrones, droneIdsKey, range]);

  /**
   * 조작 이력. 실시간 알림(토스트·카드 배너)은 지나가면 사라지므로,
   * "그때 누가 착륙시켰나"를 나중에 찾으려면 이 목록이 필요하다.
   */
  const fetchCommandLogs = async () => {
    if (noneSelected) {
      setCommandLogs([]);
      return;
    }
    setLoading(true);
    try {
      setCommandLogs(await getCommandLogs({ droneIds: droneFilter, ...rangeToServer(range) }));
    } catch (err) {
      toast.error(err.userMessage ?? '조작 이력을 불러오지 못했습니다.');
      setCommandLogs([]);
    } finally {
      setLoading(false);
    }
  };

  const detailOpen = Boolean(selectedFlight || selectedLog);
  useLayoutEffect(() => {
    // 목록으로 돌아왔을 때만 되돌린다. 상세는 따로 스크롤하므로 늘 맨 위에서 시작한다.
    if (!detailOpen && scrollRef.current) scrollRef.current.scrollTop = savedScroll.current;
  }, [detailOpen]);

  if (!isHistoryOpen) return null;

  const refresh = activeTab === 'flight' ? fetchSessions
    : activeTab === 'incident' ? fetchIncidentLogs
    : fetchCommandLogs;
  const pendingCount = incidentLogs.filter((l) => !isHandled(l.adminApprovalStatus)).length;
  const countLabel = activeTab === 'flight' ? `비행 ${sessions.length}건`
    : activeTab === 'incident' ? `사고 ${incidentLogs.length}건`
    : `조작 ${commandLogs.length}건`;

  /** 목록이 비었을 때 — 이유에 따라 다른 말을 한다 */
  const emptyFor = (tab) => {
    if (loading) return <EmptyState icon="hourglass_empty" title="불러오는 중…" />;
    if (drones.length === 0 && tab === 'flight') return <EmptyState icon="drone" title="등록된 드론이 없습니다." />;
    if (noneSelected) {
      return <EmptyState icon="filter_alt_off" title="드론을 하나 이상 선택하세요." hint="Drone Target에서 조회할 드론을 고르세요." />;
    }
    if (tab === 'flight') {
      return (
        <EmptyState
          icon="drone"
          title="이 기간에 비행 기록이 없습니다."
          hint="2026-08-14 이전 데이터는 상태 정보가 없어 조회되지 않습니다."
        />
      );
    }
    if (tab === 'incident') return <EmptyState icon="verified_user" title="이 기간에 사고 기록이 없습니다." />;
    return <EmptyState icon="terminal" title="이 기간에 조작 기록이 없습니다." />;
  };

  // ── 필터 줄 — 세 탭이 같다. 드론·기간 버튼은 폭이 고정이고 건수·새로고침은 오른쪽 끝이라
  //    무엇이 바뀌어도 서로 밀지 않는다. 불러오는 중은 아래 얇은 막대로(글자가 끼어들면 밀린다).
  const toolbar = (
    <div className="relative flex items-center gap-3 bg-white px-4 py-3 rounded-xl border border-[#c2c6d6]/70 shadow-sm shrink-0">
      <span className="text-[11px] font-bold uppercase tracking-wider text-[#727785]">Drone Target</span>
      <DroneMultiSelect drones={drones} value={selectedDrones} onChange={setSelectedDrones} />
      <span className="ml-2 text-[11px] font-bold uppercase tracking-wider text-[#727785]">Period</span>
      <DateRangePicker value={range} onChange={setRange} />
      <div className="ml-auto flex items-center gap-3">
        <span className="text-sm text-[#424754] tabular-nums whitespace-nowrap">
          {countLabel}
          {activeTab === 'incident' && pendingCount > 0 && (
            <span className="ml-2 font-bold text-amber-700">· 대기 {pendingCount}</span>
          )}
        </span>
        <button
          type="button"
          onClick={refresh}
          title="새로고침 — 「최근 N」은 지금 기준으로 다시 잡는다"
          className="w-9 h-9 flex items-center justify-center rounded-lg border border-[#c2c6d6] text-[#424754] hover:bg-[#e5eeff] hover:text-[#0058be] transition-colors cursor-pointer"
        >
          <span className={`material-symbols-outlined text-[20px] ${loading ? 'animate-spin' : ''}`}>refresh</span>
        </button>
      </div>
      {loading && <div className="absolute left-4 right-4 bottom-0 h-0.5 rounded-full bg-[#0058be]/60 animate-pulse" />}
    </div>
  );

  // ── 비행 — 날짜별로 묶은 카드. 건수가 적고 한 건의 요약이 중요하다.
  const flightGroups = [];
  for (const s of sessions) {
    const d = parseServerTime(s.startedAt);
    const key = d.toDateString();
    let g = flightGroups[flightGroups.length - 1];
    if (!g || g.key !== key) {
      g = { key, date: d, items: [] };
      flightGroups.push(g);
    }
    g.items.push(s);
  }

  const flightList = sessions.length === 0 ? emptyFor('flight') : (
    <div className="p-4 space-y-5">
      {flightGroups.map((g) => (
        <section key={g.key}>
          <h4 className="flex items-baseline gap-2 mb-2 px-1">
            <span className="text-sm font-bold text-[#0b1c30]">{fmtDayHeader(g.date)}</span>
            <span className="text-xs text-[#727785]">{g.items.length}회</span>
          </h4>
          <ul className="space-y-2">
            {g.items.map((s) => {
              const mins = Math.max(1, Math.round((parseServerTime(s.endedAt) - parseServerTime(s.startedAt)) / 60000));
              return (
                <li key={`${s.droneId}-${s.startedAt}`}>
                  <button
                    type="button"
                    onClick={() => openFlight(s)}
                    className="w-full flex items-center gap-5 px-4 py-3 rounded-lg border border-[#c2c6d6]/60 bg-white hover:border-[#0058be]/40 hover:bg-[#e5eeff]/40 transition-colors text-left cursor-pointer"
                  >
                    <div className="w-24 shrink-0"><DroneChip id={s.droneId} /></div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold text-[#0b1c30] tabular-nums">
                        {fmtClock(s.startedAt)} ~{' '}
                        {s.inProgress
                          ? <span className="text-[#0058be]">비행 중</span>
                          : fmtClock(s.endedAt)}
                        <span className="ml-2 font-medium text-[#727785]">{mins}분</span>
                      </p>
                      <p className="text-xs text-[#727785] tabular-nums truncate">
                        {s.distanceM != null && `${(s.distanceM / 1000).toFixed(2)}km · `}
                        {s.maxAltM != null && `최고 ${s.maxAltM.toFixed(0)}m · `}
                        {s.pointCount.toLocaleString()}개 지점
                      </p>
                    </div>
                    <BatteryBar start={s.batteryStart} end={s.batteryEnd} />
                    <span className="material-symbols-outlined text-[#c2c6d6] shrink-0">chevron_right</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );

  // ── 사고 — 조치할 건을 빨리 찾는 표. 분류 색 띠, 대기 중인 건은 굵게.
  const incidentTable = incidentLogs.length === 0 ? emptyFor('incident') : (
    <table className="w-full table-fixed text-sm">
      <colgroup>
        <col className="w-[8%]" />
        <col className="w-[17%]" />
        <col className="w-[12%]" />
        <col className="w-[13%]" />
        <col />
        <col className="w-[12%]" />
        <col className="w-[7%]" />
      </colgroup>
      <thead>
        <tr>
          {['ID', '발생 시각', '드론', '분류', '상황 설명', '조치', '영상'].map((h, i) => (
            <th key={h} className={`${TH} ${i === 0 || i >= 5 ? 'text-center' : 'text-left'}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {incidentLogs.map((log) => {
          const tone = classTone(log.secondClassificationResult);
          const pending = !isHandled(log.adminApprovalStatus);
          const desc = log.vlmSituationDesc || log.desc || '-';
          return (
            <tr
              key={log.eventId || log.id}
              onClick={() => { rememberScroll(); setSelectedLog(log); }}
              className={`${ROW} cursor-pointer`}
            >
              <td className="relative px-4 py-3 text-center text-xs text-[#727785] tabular-nums">
                <span className={`absolute left-0 top-2 bottom-2 w-1 rounded-r ${tone.stripe}`} />
                #{log.eventId || log.id}
              </td>
              <td className={`px-4 py-3 font-mono text-xs tabular-nums whitespace-nowrap ${pending ? 'font-bold text-[#0b1c30]' : 'text-[#424754]'}`}>
                {fmtDateTime(log.timestamp)}
              </td>
              <td className="px-4 py-3"><DroneChip id={log.droneId} /></td>
              <td className="px-4 py-3">
                <span className={`inline-block max-w-full truncate align-middle px-2 py-0.5 rounded-md border text-xs font-bold ${tone.badge}`}>
                  {log.secondClassificationResult || log.type || 'UNKNOWN'}
                </span>
              </td>
              <td className={`px-4 py-3 truncate ${pending ? 'font-semibold text-[#0b1c30]' : 'text-[#424754]'}`} title={desc}>
                {desc}
              </td>
              <td className="px-4 py-3 text-center"><StatusPill status={log.adminApprovalStatus} /></td>
              <td className="px-4 py-3 text-center">
                {log.videoClipPath
                  ? <span className="material-symbols-outlined text-[20px] text-[#0058be] align-middle">videocam</span>
                  : <span className="text-[#c2c6d6]">-</span>}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  // ── 조작 — 사고 표와 같은 로그 모양(ID·색 띠·배지·행 높이). 사고의 「분류」 자리에 명령,
  //    「상황 설명」 자리에 관제사가 온다. 띠 색은 명령 성격 — 멈추는 명령일수록 눈에 띈다.
  const commandTable = commandLogs.length === 0 ? emptyFor('command') : (
    <table className="w-full table-fixed text-sm">
      <colgroup>
        <col className="w-[8%]" />
        <col className="w-[17%]" />
        <col className="w-[12%]" />
        <col className="w-[16%]" />
        <col />
      </colgroup>
      <thead>
        <tr>
          {['ID', '실행 시각', '드론', '명령', '관제사'].map((h, i) => (
            <th key={h} className={`${TH} ${i === 0 ? 'text-center' : 'text-left'}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {commandLogs.map((c) => {
          const tone = actionTone(c.action);
          return (
            <tr key={c.id} className={ROW}>
              <td className="relative px-4 py-3 text-center text-xs text-[#727785] tabular-nums">
                <span className={`absolute left-0 top-2 bottom-2 w-1 rounded-r ${tone.stripe}`} />
                #{c.id}
              </td>
              <td className="px-4 py-3 font-mono text-xs tabular-nums whitespace-nowrap text-[#424754]">
                {fmtDateTime(c.timestamp)}
              </td>
              <td className="px-4 py-3"><DroneChip id={c.droneId} /></td>
              <td className="px-4 py-3">
                <span className={`inline-block max-w-full truncate align-middle px-2 py-0.5 rounded-md border text-xs font-bold ${tone.badge}`}>
                  {COMMAND_LABEL[c.action] ?? c.action}
                </span>
              </td>
              <td className="px-4 py-3 text-[#0b1c30] truncate" title={c.operator}>{c.operator}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#f8f9ff]/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white w-[90%] max-w-[1200px] h-[85vh] rounded-2xl shadow-xl flex flex-col overflow-hidden border border-[#c2c6d6]/70">

        {/* 헤더 */}
        <div className="flex items-center justify-between px-8 py-5 border-b border-[#c2c6d6]/50 bg-[#f8f9ff]">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-[#0058be] text-[28px]">history</span>
            <h2 className="text-2xl font-bold text-[#0b1c30] tracking-tight">System History</h2>
          </div>
          <button
            onClick={closeHistory}
            className="p-2 hover:bg-[#e5eeff] rounded-full transition-colors text-[#424754] cursor-pointer"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* 탭 메뉴 */}
        <div className="flex border-b border-[#c2c6d6]/50 px-8">
          {TABS.map(([key, label, icon]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-2 py-4 px-5 text-sm font-semibold border-b-2 transition-colors cursor-pointer ${
                activeTab === key ? 'border-[#0058be] text-[#0058be]' : 'border-transparent text-[#727785] hover:text-[#0b1c30]'
              }`}
            >
              <span className="material-symbols-outlined text-[18px]">{icon}</span>
              {label}
            </button>
          ))}
        </div>

        {/* 콘텐츠 — 필터 줄은 고정, 목록만 자기 안에서 스크롤한다.
            스크롤바 자리를 늘 비워 두어(scrollbar-gutter) 생겨도 폭이 변하지 않는다. */}
        <div className="flex-1 min-h-0 flex flex-col gap-4 p-6 bg-[#f8f9ff]/60">
          {detailOpen ? (
            // 상세 — 필터 줄 없이 한 건만. 돌아가면 필터와 목록 위치가 그대로다.
            <div className="flex-1 min-h-0 overflow-y-auto [scrollbar-gutter:stable]">
              {selectedFlight && (
                <FlightDetail
                  session={selectedFlight}
                  points={flightPoints}
                  loading={loading}
                  onBack={() => { setSelectedFlight(null); setFlightPoints([]); }}
                />
              )}
              {selectedLog && <IncidentDetail log={selectedLog} onBack={() => setSelectedLog(null)} />}
            </div>
          ) : (
            <>
              {toolbar}
              <div
                ref={scrollRef}
                className="flex-1 min-h-0 overflow-y-auto [scrollbar-gutter:stable] bg-white rounded-xl border border-[#c2c6d6]/70 shadow-sm"
              >
                {activeTab === 'flight' && flightList}
                {activeTab === 'incident' && incidentTable}
                {activeTab === 'command' && commandTable}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
