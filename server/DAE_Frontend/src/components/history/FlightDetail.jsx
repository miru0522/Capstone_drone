import React, { useMemo, useState, useEffect } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Popup } from 'react-leaflet';
import { tileConfig } from '../../config';
import TileToggle from '../common/TileToggle';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { parseServerTime, fmtClock, fmtDayHeader } from '../../utils/time';
import { droneColor } from '../../utils/droneColor';
import { DetailHeader, DroneChip, SectionLabel } from './HistoryParts';

const TILE_PREF_KEY = 'dae.mapTile.history';

/**
 * 비행 1회 상세 — 궤적 + 배터리/고도 차트.
 * HistoryPanel에 인라인으로 있던 것을 세션 단위 조회로 바꾸면서 분리했다.
 * points는 해당 세션 구간만 조회한 결과다(전체 이력이 아니다).
 */
export default function FlightDetail({ session, points, loading, onBack }) {
  // 대시보드와 쓰임이 달라(궤적 확인 vs 웨이포인트 지정) 선택을 따로 기억한다.
  const [useCarto, setUseCarto] = useState(() => {
    try { return localStorage.getItem(TILE_PREF_KEY) !== 'osm'; } catch { return true; }
  });
  useEffect(() => {
    try { localStorage.setItem(TILE_PREF_KEY, useCarto ? 'carto' : 'osm'); } catch { /* 무시 */ }
  }, [useCarto]);

  const pathPositions = useMemo(
    () => points.filter(d => d.latitude != null && d.longitude != null).map(d => [d.latitude, d.longitude]),
    [points]
  );

  const chartData = useMemo(
    () => points.map(d => ({ ...d, timeLabel: fmtClock(d.timestamp) })),
    [points]
  );

  const mapCenter = pathPositions.length > 0
    ? pathPositions[Math.floor(pathPositions.length / 2)]
    : [36.145, 128.393];

  const start = parseServerTime(session.startedAt);
  const mins = Math.max(1, Math.round((parseServerTime(session.endedAt) - start) / 60000));
  const meta = [
    `${fmtDayHeader(start)} ${fmtClock(session.startedAt)} ~ ${session.inProgress ? '비행 중' : fmtClock(session.endedAt)}`,
    `${mins}분`,
    session.distanceM != null ? `${(session.distanceM / 1000).toFixed(2)}km` : null,
    session.maxAltM != null ? `최고 ${session.maxAltM.toFixed(0)}m` : null,
    `${session.pointCount.toLocaleString()}개 지점`,
  ].filter(Boolean).join(' · ');

  return (
    <div className="flex flex-col gap-4 h-full">
      <DetailHeader
        onBack={onBack}
        title={<>비행 기록 <DroneChip id={session.droneId} /></>}
        meta={meta}
        right={loading && <span className="text-xs text-[#727785]">불러오는 중…</span>}
      />

      <div className="grid grid-cols-2 gap-4 flex-1 min-h-[460px]">
        {/* 궤적 — 지도와 같은 드론 색으로 그린다 */}
        <div className="bg-white rounded-xl border border-[#c2c6d6]/70 shadow-sm p-4 flex flex-col">
          <SectionLabel icon="route">Flight Trajectory</SectionLabel>
          <div className="flex-1 rounded-lg overflow-hidden border border-[#c2c6d6]/70 relative z-0">
            {pathPositions.length > 0 ? (
              <>
              <MapContainer center={mapCenter} zoom={16} scrollWheelZoom={true} style={{ width: '100%', height: '100%' }}>
                <TileLayer key={useCarto ? 'carto' : 'osm'} {...tileConfig(useCarto)} />
                {pathPositions.length > 1 && (
                  <Polyline positions={pathPositions} color={droneColor(session.droneId)} weight={4} opacity={0.8} />
                )}
                <Marker position={pathPositions[0]}>
                  <Popup>Start Point</Popup>
                </Marker>
                {pathPositions.length > 1 && (
                  <Marker position={pathPositions[pathPositions.length - 1]}>
                    <Popup>Last Point</Popup>
                  </Marker>
                )}
              </MapContainer>
              {/* 확대 컨트롤 바로 아래. MapContainer 밖에 두어 Leaflet 이벤트와 겹치지 않게 한다. */}
              <div className="absolute top-[82px] left-[10px] z-[1000]">
                <TileToggle useCarto={useCarto} onToggle={() => setUseCarto((v) => !v)} size="w-8 h-8" />
              </div>
              </>
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-[#f8f9ff] text-[#727785] text-sm">
                {loading ? '불러오는 중…' : '표시할 위치 데이터가 없습니다.'}
              </div>
            )}
          </div>
        </div>

        {/* 배터리 / 고도 */}
        <div className="bg-white rounded-xl border border-[#c2c6d6]/70 shadow-sm p-4 flex flex-col">
          <SectionLabel icon="monitoring">Battery &amp; Altitude</SectionLabel>
          <div className="flex-1 bg-[#f8f9ff] rounded-lg border border-[#c2c6d6]/70 p-4">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                  <XAxis dataKey="timeLabel" tick={{ fontSize: 10 }} tickMargin={10} minTickGap={30} stroke="#9ca3af" />
                  <YAxis yAxisId="left" tick={{ fontSize: 10 }} stroke="#9ca3af" domain={[0, 100]} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} stroke="#9ca3af" />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                    labelStyle={{ color: '#4b5563', fontWeight: 'bold', marginBottom: '4px' }}
                  />
                  <Legend wrapperStyle={{ paddingTop: '10px', fontSize: '12px' }} />
                  <Line yAxisId="left" type="monotone" name="Battery (%)" dataKey="battery" stroke="#f97316" strokeWidth={2} dot={false} activeDot={{ r: 6 }} />
                  <Line yAxisId="right" type="monotone" name="Altitude (m)" dataKey="altitude" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="w-full h-full flex items-center justify-center text-[#727785] text-sm">
                {loading ? '불러오는 중…' : '표시할 데이터가 없습니다.'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
