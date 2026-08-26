import React, { useState, useRef, useEffect } from 'react';
import useDroneStore from '../../store/useDroneStore';
import useUserStore from '../../store/useUserStore';
import { logout } from '../../services/api';
import Avatar from '../common/Avatar';
import toast from 'react-hot-toast';

export default function Header() {
  const toggleAlertPanel = useDroneStore((state) => state.toggleAlertPanel);
  const unreadAlertsCount = useDroneStore((state) => state.alerts.length);
  const openTTSModal = useDroneStore((state) => state.openTTSModal);
  const { openAccountModal, closeAccountModal, isAccountModalOpen, isHistoryOpen, openHistory, goToDashboard, userInfo } = useUserStore((state) => state);
  
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const settingsRef = useRef(null);

  // 로고 인트로 시퀀스 (마크 회전 → A.D.D 와이프 → 태그라인 페이드).
  //
  // CSS :hover로 돌리지 않는 이유: 마우스를 떼는 순간 애니메이션이 잘린다.
  // 클래스를 직접 붙였다 떼서, 한 번 시작하면 마우스와 무관하게 끝까지 재생한다.
  // 재생 중에 다시 올리면 처음부터 다시 돈다.
  const INTRO_MS = 2000;   // 마크 1.1s + 워드마크 0.6s(0.95s) + 태그라인 0.5s(1.45s)
  const logoRef = useRef(null);
  const introTimer = useRef(null);

  const playLogoIntro = () => {
    const el = logoRef.current;
    if (!el) return;
    el.classList.remove('logo-intro');
    void el.offsetWidth;   // ⚠️ 리플로우 강제. 없으면 클래스를 다시 붙여도 재생되지 않는다
    el.classList.add('logo-intro');
    clearTimeout(introTimer.current);
    introTimer.current = setTimeout(() => el.classList.remove('logo-intro'), INTRO_MS);
  };

  // 첫 진입 시 1회 재생
  useEffect(() => {
    playLogoIntro();
    return () => clearTimeout(introTimer.current);
  }, []);

  // 로고 클릭 = "사이트를 다시 켜는" 느낌. 실제 새로고침은 하지 않는다
  // (WebSocket 재연결·전체 재조회가 따라와 몇 초간 화면이 빈다).
  const handleLogoClick = () => {
    goToDashboard();
    playLogoIntro();
  };

  // 로그아웃: 서버 쿠키 만료 + localStorage 토큰 삭제 후 새로고침
  // (App이 다시 checkAuth를 실행하면서 로그인 화면으로 돌아간다)
  const handleLogout = async () => {
    try {
      await logout();
    } catch (e) {
      // 서버 호출이 실패해도 클라이언트 토큰은 반드시 지운다
      console.error("로그아웃 요청 실패:", e);
    } finally {
      useUserStore.getState().clearUserInfo();
      window.location.reload();
    }
  };

  useEffect(() => {
    function handleClickOutside(event) {
      if (settingsRef.current && !settingsRef.current.contains(event.target)) {
        setIsSettingsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [settingsRef]);

  return (
    <header className="bg-[#f8f9ff] shadow-sm flex justify-between items-center w-full px-8 h-20 z-[300] relative">
      <div className="flex items-center gap-4">
        {/* 로고를 누르면 대시보드로 — 좌측 상단 로고는 홈으로 간다는 게 오래된 웹 관례다.
            지금까지는 눌러도 반응이 없어 어색했다. */}
        <div
          ref={logoRef}
          className="logo-home flex items-center cursor-pointer select-none"
          onMouseEnter={playLogoIntro}
          onClick={handleLogoClick}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goToDashboard(); } }}
          title="대시보드로 이동"
        >
          <svg width="40" height="40" viewBox="0 0 120 120" role="img" aria-hidden="true" className="logo-mark mr-2">
            <defs>
              <mask id="addEyeInv">
                <rect x="0" y="0" width="120" height="120" fill="#FFFFFF"/>
                <polygon points="60,47 73,60 60,73 47,60" fill="#000000"/>
              </mask>
            </defs>
            <g fill="#0E0E0E" mask="url(#addEyeInv)">
              <rect x="40" y="16" width="40" height="7"/>
              <rect x="40" y="97" width="40" height="7"/>
              <rect x="16" y="40" width="7" height="40"/>
              <rect x="97" y="40" width="7" height="40"/>
              <rect x="51" y="22" width="18" height="76"/>
              <rect x="22" y="51" width="76" height="18"/>
            </g>
            <polygon points="60,54 66,60 60,66 54,60" fill="#0E0E0E"/>
          </svg>
          <div className="flex flex-col justify-center">
            <h1 className="logo-word text-3xl font-black tracking-tighter text-[#0E0E0E] leading-none">A.D.D</h1>
            {/* 로고 원본의 태그라인. 좁은 화면에서는 메뉴를 밀어내므로 숨긴다. */}
            <p className="logo-sub hidden lg:block mt-1 text-[9px] font-medium text-[#8A8A85] uppercase whitespace-nowrap leading-none"
               style={{ letterSpacing: '0.14em' }}>
              Anomaly&nbsp;·&nbsp;Detection&nbsp;·&nbsp;Drone
            </p>
          </div>
        </div>
        <nav className="hidden md:flex ml-8 items-center gap-6">
          <a onClick={goToDashboard} className={`${!isAccountModalOpen && !isHistoryOpen ? 'text-[#0058be] border-b-2 border-[#0058be]' : 'text-[#424754] hover:bg-[#eff4ff] transition-colors rounded-lg'} font-medium text-sm py-2 px-4 cursor-pointer`}>DASHBOARD</a>
          <a onClick={openHistory} className={`${isHistoryOpen ? 'text-[#0058be] border-b-2 border-[#0058be]' : 'text-[#424754] hover:bg-[#eff4ff] transition-colors rounded-lg'} font-medium text-sm py-2 px-4 cursor-pointer`}>HISTORY</a>
          <a onClick={openAccountModal} className={`${isAccountModalOpen ? 'text-[#0058be] border-b-2 border-[#0058be]' : 'text-[#424754] hover:bg-[#eff4ff] transition-colors rounded-lg'} font-medium text-sm py-2 px-4 cursor-pointer`}>ACCOUNTS</a>
        </nav>
      </div>
      <div className="flex items-center gap-4 relative">
        <button 
          onClick={toggleAlertPanel}
          className="relative material-symbols-outlined p-2 text-[#424754] hover:bg-[#eff4ff] rounded-full transition-colors cursor-pointer active:scale-95 duration-200"
        >
          notifications
          {unreadAlertsCount > 0 && (
            <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-red-500 rounded-full border-2 border-white"></span>
          )}
        </button>
        
        {/* 환경설정 드롭다운 */}
        <div className="relative" ref={settingsRef}>
          <button 
            onClick={() => setIsSettingsOpen(!isSettingsOpen)}
            className={`material-symbols-outlined p-2 rounded-full transition-colors cursor-pointer active:scale-95 duration-200 ${isSettingsOpen ? 'bg-[#dae2fd] text-[#0058be]' : 'text-[#424754] hover:bg-[#eff4ff]'}`}
            title="환경설정"
          >
            settings
          </button>
          
          {isSettingsOpen && (
            <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden py-1 z-[1000] animate-in fade-in slide-in-from-top-2 duration-200">
              <div className="px-4 py-2 border-b border-gray-100">
                <p className="text-xs font-bold text-gray-500">SYSTEM SETTINGS</p>
              </div>
              
              <div className="p-2 border-b border-gray-100">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                >
                  <span className="material-symbols-outlined text-[18px]">logout</span>
                  로그아웃
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 프로필 사진이 없으면 Avatar가 "하늘색 배경 + 아이디" 기본 아바타를 그린다 */}
        <button
          onClick={openAccountModal}
          title="계정 관리"
          className="ml-2 rounded-full hover:ring-2 hover:ring-[#dae2fd] transition-all active:scale-95 duration-200"
        >
          <Avatar src={userInfo?.profileImage} userId={userInfo?.userId} size={40} />
        </button>
      </div>
    </header>
  );
}
