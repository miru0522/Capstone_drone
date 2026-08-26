import React, { useEffect, useState } from 'react';
import { Toaster } from 'react-hot-toast';
import './index.css';

// Components
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import DroneMap from './components/map/DroneMap';
import AlertPanel from './components/alerts/AlertPanel';
import TTSApprovalModal from './components/modals/TTSApprovalModal';
import MissionDoneModal from './components/modals/MissionDoneModal';
import LiveStreamModal from './components/modals/LiveStreamModal';
import CancelPatrolModal from './components/modals/CancelPatrolModal';
import DroneStatusModal from './components/modals/DroneStatusModal';
import DroneManagementModal from './components/modals/DroneManagementModal';
import DroneRegisterModal from './components/modals/DroneRegisterModal';
import StartPatrolModal from './components/modals/StartPatrolModal';
import RouteManagerModal from './components/modals/RouteManagerModal';
import LoginScreen from './components/layout/LoginScreen';

// Services
import { connectWebSocket, disconnectWebSocket } from './services/websocket';
import { checkAuth, getMyDrones, getEvents } from './services/api';
import useDroneStore from './store/useDroneStore';
import useUserStore from './store/useUserStore';
import AccountManagementModal from './components/modals/AccountManagementModal';
import HistoryPanel from './components/layout/HistoryPanel';

// 텔레메트리가 이 시간 이상 끊기면 OFFLINE으로 간주한다 (드론은 1초 주기로 발행)
const TELEMETRY_TIMEOUT_MS = 10000;

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const setUserInfo = useUserStore((state) => state.setUserInfo);

  // 인증 상태 확인
  const verifyAuth = async () => {
    try {
      const userInfo = await checkAuth();
      setUserInfo(userInfo);
      setIsLoggedIn(true);
    } catch (e) {
      setIsLoggedIn(false);
      useUserStore.getState().clearUserInfo();
    } finally {
      setIsCheckingAuth(false);
    }
  };

  useEffect(() => {
    verifyAuth();
  }, []);

  const handleLoginSuccess = async () => {
    console.log("=== [DEBUG] handleLoginSuccess 호출됨! 내 정보 다시 갱신 시작 ===");
    await verifyAuth(); // 로그인 직후 내 정보 다시 땡겨오기
    console.log("=== [DEBUG] 내 정보 갱신 완료! ===");
  };

  // 앱 실행 시 WebSocket 연결 (로그인 후에만)
  useEffect(() => {
    if (isLoggedIn) {
      connectWebSocket();
      return () => {
        disconnectWebSocket();
      };
    }
  }, [isLoggedIn]);

  // 로그인 후 DB에 등록된 드론을 목록에 미리 채운다.
  // 전원이 꺼져 있어도 OFFLINE 상태로 보이고, 신호가 오면 자동으로 갱신된다.
  useEffect(() => {
    if (!isLoggedIn) return;
    getMyDrones()
      .then((list) => useDroneStore.getState().seedRegisteredDrones(list || []))
      .catch(() => {/* 조회 실패 시 텔레메트리로만 목록을 구성한다 */});
  }, [isLoggedIn]);

  // 미조치 VLM 경보를 서버에서 복원한다.
  // 경보는 event_logs에 있으므로 새로고침해도 사라지면 안 된다 —
  // 승인 대기 중인 이상상황을 화면 새로고침 한 번으로 놓치면 안 되기 때문이다.
  // (시스템 알림은 클라이언트가 만든 것이라 localStorage에서 복원된다)
  useEffect(() => {
    if (!isLoggedIn) return;
    getEvents()
      .then((events) => {
        (events || [])
          .filter((e) => !e.adminApprovalStatus)   // 아직 승인도 반려도 안 된 건만
          .forEach((e) => useDroneStore.getState().addAlert({
            id: e.eventId,
            type: 'Critical',
            time: e.timestamp ? new Date(e.timestamp).toLocaleTimeString('ko-KR', { hour12: false }) : '',
            title: `VLM Alarm: ${e.secondClassificationResult || '이상 상황'}`,
            desc: e.vlmSituationDesc,
            ttsText: e.vlmTtsCandidate,
            videoUrl: e.videoClipPath,
            source: e.droneId || 'VLM',
          }));
      })
      .catch(() => {/* 복원 실패는 조용히 넘긴다. 실시간 수신은 계속된다 */});
  }, [isLoggedIn]);

  // 신호가 끊긴 드론을 주기적으로 OFFLINE 처리
  useEffect(() => {
    if (!isLoggedIn) return;
    const timer = setInterval(() => {
      useDroneStore.getState().markStaleDronesOffline(TELEMETRY_TIMEOUT_MS);
    }, 5000);
    return () => clearInterval(timer);
  }, [isLoggedIn]);

  if (isCheckingAuth) {
    return <div className="h-screen w-full bg-[#0b1c30] flex items-center justify-center">
      <span className="material-symbols-outlined animate-spin text-white text-4xl">progress_activity</span>
    </div>;
  }

  // 미인증 상태에서는 대시보드를 아예 마운트하지 않는다.
  // (오버레이로만 가리면 Sidebar 등이 먼저 마운트되어 인증 필요한 API가 403으로 실패한다)
  if (!isLoggedIn) {
    return <LoginScreen onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="bg-[#f8f9ff] text-[#0b1c30] font-sans overflow-hidden h-screen flex flex-col">
      <Toaster position="top-center" toastOptions={{ duration: 4000 }} />
      <Header />

      <div className="flex flex-1 overflow-hidden relative">
        <Sidebar />
        
        <main className="flex-1 flex flex-col relative bg-[#eff4ff]">
          <div className="flex-1 relative">
            {/* 중앙 지도 뷰 */}
            <DroneMap />
            {/* 모달 시스템 */}
            <TTSApprovalModal />
      <MissionDoneModal />
            <LiveStreamModal />
            <CancelPatrolModal />
            <DroneStatusModal />
            <DroneManagementModal />
            <DroneRegisterModal />
            <StartPatrolModal />
            <RouteManagerModal />
            <AccountManagementModal />
            <HistoryPanel />
          </div>
        </main>

        <AlertPanel />
      </div>
    </div>
  );
}

export default App;
