import axios from 'axios';
import { getApiBaseUrl } from '../config';

const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 5000,
  withCredentials: true,
});



export const login = async (id, pwd) => {
  try {
    const res = await api.post('/auth/login', { userId: id, pwd });
    return res.data;
  } catch (error) {
    console.error("Login Error:", error);
    throw error;
  }
};

export const logout = async () => {
  try {
    const res = await api.post('/auth/logout');
    return res.data;
  } catch (error) {
    console.error("Logout Error:", error);
    throw error;
  }
};

// DB에 등록된 내 드론 목록 (전원이 꺼져 있어도 조회된다)
export const getMyDrones = async () => {
  try {
    const res = await api.get('/drones');
    return res.data;
  } catch (error) {
    console.error("Get My Drones Error:", error);
    throw error;
  }
};

export const checkAuth = async () => {
  try {
    const res = await api.get('/users/me');
    return res.data;
  } catch (error) {
    console.error("Check Auth Error:", error);
    throw error;
  }
};


/** 이벤트 전체 목록. HISTORY와 미조치 경보 복원이 함께 쓴다. */
export const getEvents = async () => {
  const res = await api.get('/events');
  return res.data;
};

export const approveTTS = async (eventId) => {
  try {
    const res = await api.post(`/events/${eventId}/tts-approval`);
    return res.data;
  } catch (error) {
    console.error("TTS Approval Error:", error);
    throw error;
  }
};

export const startPatrol = async (droneId) => {
  try {
    const res = await api.post(`/drones/${droneId}/commands/start`);
    return res.data;
  } catch (error) {
    console.error("Start Patrol Error:", error);
    throw error;
  }
};

export const resumePatrol = async (droneId) => {
  try {
    const res = await api.post(`/drones/${droneId}/commands/resume`);
    return res.data;
  } catch (error) {
    console.error("Resume Patrol Error:", error);
    throw error;
  }
};

export const cancelPatrol = async (droneId) => {
  try {
    const res = await api.post(`/drones/${droneId}/commands/cancel`);
    return res.data;
  } catch (error) {
    console.error("Cancel Patrol Error:", error);
    throw error;
  }
};

export const emergencyStop = async (droneId) => {
  try {
    const res = await api.post(`/drones/${droneId}/commands/emergency-stop`);
    return res.data;
  } catch (error) {
    console.error("Emergency Stop Error:", error);
    throw error;
  }
};

export const pausePatrol = async (droneId) => {
  try {
    const res = await api.post(`/drones/${droneId}/commands/pause`);
    return res.data;
  } catch (error) {
    console.error("Pause Patrol Error:", error);
    throw error;
  }
};

// ── 실시간 영상 (2026-08-22 드론팀 합의) ─────────────────────────
// 드론은 REQUEST_STREAM을 받기 전에는 한 장도 보내지 않는다.
// 화면을 닫을 때 stopStream을 반드시 불러야 드론이 배터리를 아낀다.
// (못 부르고 닫혀도 서버가 410으로 멈추게 하지만, 그건 안전망이다)
export const startStream = async (droneId) => {
  const res = await api.post(`/drones/${droneId}/stream/start`);
  return res.data;   // { streamId }
};

export const stopStream = async (droneId) => {
  try {
    await api.post(`/drones/${droneId}/stream/stop`);
  } catch (error) {
    // 화면을 닫는 길에 부르는 것이라 실패해도 사용자에게 알릴 것이 없다.
    console.error("Stop Stream Error:", error);
  }
};

export const landPatrol = async (droneId) => {
  try {
    const res = await api.post(`/drones/${droneId}/commands/land`);
    return res.data;
  } catch (error) {
    console.error("Land Patrol Error:", error);
    throw error;
  }
};

export const returnToBase = async (droneId) => {
  try {
    const res = await api.post(`/drones/${droneId}/commands/return`);
    return res.data;
  } catch (error) {
    console.error("Return to Base Error:", error);
    throw error;
  }
};



/**
 * 드론에 순찰 경로를 지정한다.
 *
 * 지도 라이브러리(Leaflet)는 lng를 쓰지만, 드론 계약은 lon이다
 * (텔레메트리의 lon_deg와 맞추기 위해 2026-08-20 통일).
 * 여기서 한 번만 변환해 두면 화면 코드는 계속 lng를 쓸 수 있다.
 *
 * alt_agl은 지면 기준 목표고도다. 지정하지 않으면 서버가 기본값(50m)을 넣고,
 * 드론은 자체 최소 안전고도(20m)를 하한선으로 유지한다.
 */
export const saveRoute = async (droneId, waypoints) => {
  try {
    const payload = waypoints.map((p) => ({
      lat: p.lat,
      lon: p.lon ?? p.lng,
      ...(p.alt_agl != null && { alt_agl: p.alt_agl }),
    }));
    const res = await api.put(`/drones/${droneId}/route`, payload);
    return res.data;
  } catch (error) {
    console.error("Save Route Error:", error);
    throw error;
  }
};

/**
 * 서버가 이 드론에게 마지막으로 지시한 경로 → [{lat, lng}, ...]
 * ⚠️ 드론이 지금도 들고 있다는 보장은 아니다. 실제 보유 여부는 텔레메트리의 hasRoute가 진실이다.
 */
export const getDroneRoute = async (droneId) => {
  try {
    const res = await api.get(`/drones/${droneId}/route`);
    return Array.isArray(res.data) ? res.data : [];
  } catch (error) {
    console.error("Get Drone Route Error:", error);
    return [];
  }
};

/**
 * 드론의 스테이션(기지) 좌표를 지정한다.
 * 경도 키는 드론 계약에 맞춰 lon으로 보낸다(화면은 지도 관례상 lng를 쓴다).
 */
export const saveStation = async (droneId, lat, lng) => {
  try {
    const res = await api.put(`/drones/${droneId}/station`, { lat, lon: lng });
    return res.data;
  } catch (error) {
    console.error("Set Station Error:", error);
    throw error;
  }
};


export const registerDrone = async (formData) => {
  try {
    const res = await api.post('/drones', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  } catch (error) {
    console.error("Register Drone Error:", error);
    throw error;
  }
};

// ==========================================
// 사용자 및 계정 관리 API
// ==========================================

export const checkUserId = async (userId) => {
  try {
    const res = await api.get(`/auth/check-id?userId=${userId}`);
    return res.data; // { exists: boolean }
  } catch (error) {
    console.error("Check ID Error:", error);
    throw error;
  }
};

export const registerUser = async (userData) => {
  try {
    const res = await api.post('/auth/signup', userData);
    return res.data;
  } catch (error) {
    console.error("Register User Error:", error);
    throw error;
  }
};

export const verifyPassword = async (pwd) => {
  try {
    const res = await api.post('/auth/verify-password', { pwd });
    return res.data;
  } catch (error) {
    console.error("Verify Password Error:", error);
    throw error;
  }
};

export const updateMyInfo = async (userData) => {
  try {
    const res = await api.put('/users/me', userData);
    return res.data;
  } catch (error) {
    console.error("Update Info Error:", error);
    throw error;
  }
};

export const deleteMyAccount = async () => {
  try {
    const res = await api.delete('/users/me');
    return res.data;
  } catch (error) {
    console.error("Delete Account Error:", error);
    throw error;
  }
};

// ==========================================
// 관리자(Admin) 전용 API
// ==========================================

export const getAdminUsers = async (status = '') => {
  try {
    const url = status ? `/admin/users?status=${status}` : '/admin/users';
    const res = await api.get(url);
    return res.data; // User 객체 배열
  } catch (error) {
    console.error("Get Admin Users Error:", error);
    throw error;
  }
};

export const approveUser = async (id) => {
  try {
    const res = await api.post(`/admin/users/${id}/approve`);
    return res.data;
  } catch (error) {
    console.error("Approve User Error:", error);
    throw error;
  }
};

export const rejectUser = async (id) => {
  try {
    const res = await api.post(`/admin/users/${id}/reject`);
    return res.data;
  } catch (error) {
    console.error("Reject User Error:", error);
    throw error;
  }
};

export const disableUser = async (id) => {
  try {
    const res = await api.post(`/admin/users/${id}/disable`);
    return res.data;
  } catch (error) {
    console.error("Disable User Error:", error);
    throw error;
  }
};

export const changeUserRole = async (id, role) => {
  try {
    const res = await api.patch(`/admin/users/${id}/role`, { role });
    return res.data;
  } catch (error) {
    console.error("Change Role Error:", error);
    throw error;
  }
};

export const deleteUserByAdmin = async (id) => {
  try {
    const res = await api.delete(`/admin/users/${id}`);
    return res.data;
  } catch (error) {
    console.error("Delete User Error:", error);
    throw error;
  }
};

export const changeUserPasswordByAdmin = async (id, pwd) => {
  try {
    const res = await api.patch(`/admin/users/${id}/password`, { pwd });
    return res.data;
  } catch (error) {
    console.error("Change Password Error:", error);
    throw error;
  }
};

export const updateUserByAdmin = async (id, data) => {
  try {
    const res = await api.put(`/admin/users/${id}/profile`, data);
    return res.data;
  } catch (error) {
    console.error("Update User Profile Error:", error);
    throw error;
  }
};

export const getUserDroneSettings = async () => {
  try {
    const res = await api.get('/users/me/drone-settings');
    return res.data;
  } catch (error) {
    console.error("Get User Settings Error:", error);
    throw error;
  }
};

export const updateUserDroneSettings = async (settingsArray) => {
  try {
    const res = await api.put('/users/me/drone-settings', settingsArray);
    return res.data;
  } catch (error) {
    console.error("Update User Settings Error:", error);
    throw error;
  }
};

/* ── 순찰 경로(Route) 관리 ────────────────────────────────────────────
   경로는 팀 공용 자산으로 백엔드 DB에 저장된다. 조회는 전원, 생성·수정·삭제는 ADMIN만.
   (Route.user는 소유자가 아니라 만든 사람 기록이다.) 경로 자체(Route)와 지점 목록(Waypoint)이
   분리되어 있어, 새 경로를 만들 땐 ① Route 생성으로 routeId를 받고 ② 지점을 붙인다. */

/** 순찰 경로 목록(팀 공용, 전원 조회 가능) → [{ routeId, routeName, routeComment }] */
export const getRoutes = async () => {
  try {
    const res = await api.get('/patrol-routes');
    return res.data;
  } catch (error) {
    console.error("Get Routes Error:", error);
    throw error;
  }
};

/** 경로의 지점 목록 → [{ step, latitude, longitude, address }] */
export const getWaypoints = async (routeId) => {
  try {
    const res = await api.get(`/patrol-routes/${routeId}/waypoints`);
    return res.data;
  } catch (error) {
    console.error("Get Waypoints Error:", error);
    throw error;
  }
};

/** 경로 이름 중복 확인 (전역). true면 이미 있는 이름이다. */
export const checkRouteName = async (routeName) => {
  const res = await api.get('/patrol-routes/check-name', { params: { routeName } });
  return res.data === true;
};

/** 빈 경로를 만들고 routeId를 돌려준다. 지점은 이어서 saveWaypoints로 채운다. */
export const createRoute = async (routeName, routeComment) => {
  const res = await api.post('/patrol-routes', { routeName, routeComment });
  const routeId = res.data?.routeId;
  if (!routeId) throw new Error(res.data?.message || '경로 생성에 실패했습니다.');
  return routeId;
};

/**
 * 경로의 지점 목록을 저장한다.
 * @param {{lat:number, lng:number}[]} points 지도에서 찍은 순서대로
 */
export const saveWaypoints = async (routeId, points) => {
  const res = await api.put(`/patrol-routes/${routeId}/waypoints`, points.map((p, i) => ({
    step: i + 1,
    latitude: p.lat,
    longitude: p.lng,
    address: null,
  })));
  return res.data;
};

/** 경로 이름·설명 수정 (ADMIN 전용). 지점은 saveWaypoints로 따로 저장한다. */
export const updateRoute = async (routeId, routeName, routeComment) => {
  try {
    const res = await api.patch(`/patrol-routes/${routeId}`, { routeName, routeComment });
    return res.data;
  } catch (error) {
    console.error("Update Route Error:", error);
    throw error;
  }
};

export const deleteRoute = async (routeId) => {
  try {
    const res = await api.delete(`/patrol-routes/${routeId}`);
    return res.data;
  } catch (error) {
    console.error("Delete Route Error:", error);
    throw error;
  }
};

/** 프로필 사진 변경. 반환값의 profileImage를 그대로 스토어에 반영하면 된다. */
export const uploadProfileImage = async (file) => {
  const formData = new FormData();
  formData.append('image', file);
  try {
    // Content-Type은 지정하지 않는다. 브라우저가 multipart 경계값을 직접 붙여야 한다.
    const res = await api.put('/users/me/profile-image', formData);
    return res.data;
  } catch (error) {
    console.error("Upload Profile Image Error:", error);
    throw error;
  }
};

/** 프로필 사진 제거 → 기본 아바타(하늘색 + 아이디)로 되돌린다. */
export const resetProfileImage = async () => {
  try {
    const res = await api.delete('/users/me/profile-image');
    return res.data;
  } catch (error) {
    console.error("Reset Profile Image Error:", error);
    throw error;
  }
};

export default api;
