import React, { useMemo } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Popup } from 'react-leaflet';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const fmtTime = (t) => new Date(t).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });

/**
 * 비행 1회 상세 — 궤적 + 배터리/고도 차트.
 * HistoryPanel에 인라인으로 있던 것을 세션 단위 조회로 바꾸면서 분리했다.
 * points는 해당 세션 구간만 조회한 결과다(전체 이력이 아니다).
 */
export default function FlightDetail({ session, points, loading, onBack }) {
  const pathPositions = useMemo(
    () => points.filter(d => d.latitude != null && d.longitude != null).map(d => [d.latitude, d.longitude]),
    [points]
  );

  const chartData = useMemo(
    () => points.map(d => ({
      ...d,
      timeLabel: new Date(d.timestamp).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    })),
    [points]
  );

  const mapCenter = pathPositions.length > 0
    ? pathPositions[Math.floor(pathPositions.length / 2)]
    : [36.145, 128.393];

  return (
    <div className="flex flex-col gap-6 h-full">
      {/* 헤더 */}
      <div className="flex items-center gap-4 bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
        <button
          onClick={onBack}
          className="p-2 bg-white border border-gray-300 text-gray-600 hover:bg-gray-50 rounded-lg transition-colors flex items-center justify-center"
          title="목록으로"
        >
          <span className="material-symbols-outlined text-[20px]">arrow_back</span>
        </button>
        <div>
          <h3 className="font-bold text-gray-800">
            {fmtTime(session.startedAt)} ~ {session.inProgress ? '비행 중' : fmtTime(session.endedAt)}
          </h3>
          <p className="text-xs text-gray-500">
            {new Date(session.startedAt).toLocaleDateString('ko-KR')} · {session.pointCount}개 지점
            {session.distanceM != null && ` · ${(session.distanceM / 1000).toFixed(2)}km`}
          </p>
        </div>
        {loading && <span className="ml-auto text-sm text-gray-400">불러오는 중...</span>}
      </div>

      <div className="grid grid-cols-2 gap-6 flex-1 h-[500px]">
        {/* 궤적 */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex flex-col h-full">
          <h3 className="font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <span className="material-symbols-outlined text-green-600">route</span>
            Flight Trajectory
          </h3>
          <div className="flex-1 rounded-lg overflow-hidden border border-gray-200 relative z-0">
            {pathPositions.length > 0 ? (
              <MapContainer center={mapCenter} zoom={16} scrollWheelZoom={true} style={{ width: '100%', height: '100%' }}>
                <TileLayer
                  attribution='&copy; OpenStreetMap'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                {pathPositions.length > 1 && (
                  <Polyline positions={pathPositions} color="blue" weight={4} opacity={0.7} />
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
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-gray-50 text-gray-400 text-sm">
                표시할 위치 데이터가 없습니다.
              </div>
            )}
          </div>
        </div>

        {/* 배터리 / 고도 */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex flex-col h-full">
          <h3 className="font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <span className="material-symbols-outlined text-orange-500">monitoring</span>
            Battery &amp; Altitude
          </h3>
          <div className="flex-1 bg-gray-50 rounded-lg border border-gray-200 p-4">
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
              <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                표시할 데이터가 없습니다.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

