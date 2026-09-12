/**
 * API 주소 동적 할당 파일
 * 프론트가 Nginx 뒤에서 서빙되므로 항상 same-origin(상대경로)을 사용합니다.
 */
export const getApiBaseUrl = () => '';

/**
 * 지도 타일 제공자.
 *
 * CARTO는 2026-08 무렵부터 무료 공개 CDN에도 API 키를 요구한다 —
 * 키 없이 쓰면 타일에 "API KEY REQUIRED" 워터마크가 새겨져 온다.
 * 키는 빌드 시점에 박히므로 바꾸면 프론트를 다시 빌드해야 한다.
 *
 * 두 벌을 모두 내보내 관제사가 화면에서 바꿀 수 있게 한다.
 * CARTO는 옅어서 드론 마커와 경로가 잘 보이고,
 * OSM은 도로·건물이 자세해 웨이포인트를 찍을 때 유리하다.
 */
const CARTO_KEY = import.meta.env.VITE_CARTO_API_KEY;

/** 키가 없으면 CARTO를 고를 수 없다 — 화면에서 토글 자체를 숨긴다. */
export const CARTO_AVAILABLE = Boolean(CARTO_KEY);

// 매개변수 이름은 key 다 (api_key 아님). CARTO 문서의 URL 형태를 그대로 따른다.
export const CARTO_TILES = {
  url: `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png?key=${CARTO_KEY}`,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: 'abcd',   // CARTO는 네 개다 (Leaflet 기본값은 abc 세 개)
  maxZoom: 20,
};

export const OSM_TILES = {
  url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  subdomains: 'abc',
  maxZoom: 19,
};

/** 키가 없으면 무엇을 고르든 OSM으로 떨어진다. */
export const tileConfig = (useCarto) =>
  (useCarto && CARTO_AVAILABLE) ? CARTO_TILES : OSM_TILES;
