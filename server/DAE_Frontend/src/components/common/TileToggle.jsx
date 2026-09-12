import React from 'react';
import { CARTO_AVAILABLE } from '../../config';

/**
 * 지도 타일 전환 버튼.
 *
 * CARTO는 옅어서 드론 마커와 비행 궤적이 잘 보이고,
 * OSM은 도로·건물이 자세해 웨이포인트를 찍거나 지형을 볼 때 유리하다.
 * 어느 하나로 고정할 이유가 없어 화면에서 바꾸게 한다.
 *
 * CARTO 키가 없으면 고를 것이 없으므로 아무것도 그리지 않는다.
 */
export default function TileToggle({ useCarto, onToggle, className = '', size = 'w-12 h-12' }) {
  if (!CARTO_AVAILABLE) return null;

  return (
    <button
      type="button"
      onClick={onToggle}
      className={`${size} flex items-center justify-center bg-white rounded-full shadow-md border border-gray-300 hover:bg-gray-50 text-gray-600 transition-colors cursor-pointer ${className}`}
      title={useCarto ? '상세 지도로 전환 (OSM)' : '관제 지도로 전환 (CARTO)'}
    >
      <span className="material-symbols-outlined text-[20px]">
        {useCarto ? 'layers' : 'layers_clear'}
      </span>
    </button>
  );
}
