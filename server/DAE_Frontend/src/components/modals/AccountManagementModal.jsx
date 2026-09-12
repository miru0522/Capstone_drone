import React, { useState, useEffect } from 'react';
import useUserStore from '../../store/useUserStore';
import useDroneStore from '../../store/useDroneStore';
import { verifyPassword } from '../../services/api';
import MyAccountTab from './MyAccountTab';
import UserAdminTab from './UserAdminTab';

/**
 * 계정 화면의 껍데기 — 탭 전환과 비밀번호 재확인만 맡는다.
 *
 * 예전에는 한 파일 601줄에 「내 정보」와 「남의 계정 관리」가 함께 쌓여 있었다.
 * 성격이 다른 두 일이 같은 스크롤에 있어 VIEWER에게도 쓸 수 없는 관리자 표가
 * 딸려 나왔다. 탭으로 갈라 각각 MyAccountTab / UserAdminTab 이 맡는다.
 *
 * 비밀번호 재확인은 <b>볼 때가 아니라 바꿀 때</b> 받는다. 예전에는 창을 열
 * 때마다 받아서, 사진 한 장 바꾸려도 비밀번호를 넣어야 했다.
 */
export default function AccountManagementModal() {
  const { isAccountModalOpen, closeAccountModal, userInfo } = useUserStore();
  const setHasUnsavedChanges = useDroneStore((state) => state.setHasUnsavedChanges);

  const isAdmin = userInfo?.role === 'ADMIN';
  const [tab, setTab] = useState('me');

  // 재확인은 창을 닫을 때까지 한 번만 받는다.
  const [isVerified, setIsVerified] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // 확인이 끝나면 이어서 실행할 동작. 확인을 요구한 이유가 무엇이었는지 기억한다.
  const [pendingAction, setPendingAction] = useState(null);

  // 창을 닫으면 확인 상태를 버린다. 자리를 비운 사이 남이 열어도
  // 곧바로 계정을 바꿀 수 없어야 한다.
  useEffect(() => {
    if (!isAccountModalOpen) {
      setIsVerified(false);
      setPendingAction(null);
      setPassword('');
      setError('');
      setTab('me');
    }
  }, [isAccountModalOpen]);

  /**
   * 계정을 바꾸는 동작을 감싼다. 확인이 끝나 있으면 바로 실행하고,
   * 아니면 확인 층을 띄운 뒤 통과했을 때 실행한다.
   */
  const requireVerify = (action) => {
    if (isVerified) {
      action();
      return;
    }
    setPassword('');
    setError('');
    setPendingAction(() => action);
  };

  const handleVerify = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      await verifyPassword(password);
      setIsVerified(true);
      const next = pendingAction;
      setPendingAction(null);
      setPassword('');
      // 확인을 요구한 그 동작을 이어서 실행한다. 다시 누르게 하지 않는다.
      if (next) next();
    } catch {
      setError('비밀번호가 일치하지 않습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setHasUnsavedChanges(false);
    closeAccountModal();
  };

  if (!isAccountModalOpen) return null;

  const TAB = (id, label, icon) => (
    <button
      key={id}
      onClick={() => setTab(id)}
      className={`px-4 py-2 text-sm font-bold rounded-lg transition-all duration-150 flex items-center gap-1.5 cursor-pointer ${
        tab === id
          ? 'bg-[#e5eeff] text-[#0058be]'
          : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
      }`}
    >
      <span className="material-symbols-outlined text-[18px]">{icon}</span>
      {label}
    </button>
  );

  // Tailwind v4에서 bg-opacity-* 가 삭제됐다. 예전 문법을 쓰면 투명도가
  // 조용히 무시되어 남색이 꽉 찬다 — 슬래시 문법을 써야 한다.
  // HISTORY 패널과 같은 층위이므로 같은 밝은 반투명으로 맞춘다.
  // 어두운 막은 경보 팝업 같은 모달에 남겨둔다.
  return (
    <div className="absolute inset-0 z-[200] flex items-center justify-center bg-[#f8f9ff]/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-xl shadow-2xl p-6 relative w-full max-w-2xl animate-in fade-in zoom-in duration-200">
        <button
          onClick={handleClose}
          aria-label="닫기"
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined">close</span>
        </button>

        <h2 className="text-xl font-black tracking-tight text-gray-900 flex items-center gap-2 mb-4">
          <span className="material-symbols-outlined text-[#0058be]">manage_accounts</span>
          계정
        </h2>

        {/* ADMIN이 아니면 탭이 하나뿐이라 굳이 보여주지 않는다 */}
        {isAdmin && (
          <div className="flex gap-1 mb-4 border-b pb-3">
            {TAB('me', '내 계정', 'person')}
            {TAB('users', '사용자 관리', 'group')}
          </div>
        )}

        {/* 스크롤 영역이 바깥(여기)과 표 안쪽 둘이다. 탭마다 내용 높이가 달라
            이 스크롤바가 생겼다 사라지면서 안쪽 표의 가용 폭이 함께 달라졌다.
            안쪽만 gutter 를 줘도 바깥이 움직이면 열이 밀린다. */}
        <div className="flex flex-col h-[500px] overflow-y-auto overflow-x-hidden [scrollbar-gutter:stable]">
          {tab === 'me' || !isAdmin
            ? <MyAccountTab requireVerify={requireVerify} />
            : <UserAdminTab requireVerify={requireVerify} />}
        </div>

        {/* 비밀번호 재확인 층 — 바꾸려는 동작이 있을 때만 뜬다.
            ⚠️ 카드 안에 둔다. 카드 밖에 두면 화면 전체가 어두워졌다가, 확인이
            끝나고 뜨는 프로필 수정 층(카드만 덮는다)에서 범위가 갑자기 줄어
            이질감이 생긴다. 덮는 면적을 같게 맞춘다. */}
        {pendingAction && (
          <div className="absolute inset-0 z-[260] flex items-center justify-center bg-black/40 backdrop-blur-sm rounded-xl">
          <div className="bg-white p-6 rounded-xl shadow-2xl border border-blue-100 w-[380px] animate-in fade-in zoom-in duration-200">
            <div className="flex items-center gap-2 mb-4 border-b pb-3">
              <span className="material-symbols-outlined text-[#0058be] text-[20px]">lock</span>
              <span className="text-sm font-bold text-gray-800">비밀번호 확인</span>
            </div>
            <p className="text-xs text-gray-600 mb-4">
              계정을 변경하려면 현재 계정의 비밀번호를 다시 한 번 입력해 주세요.
            </p>
            <form onSubmit={handleVerify} className="space-y-3">
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                autoFocus
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-100 focus:border-[#0058be] outline-none text-center tracking-widest transition-all"
                placeholder="비밀번호"
                required
              />
              {error && <p className="text-red-500 text-xs text-center font-bold">{error}</p>}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => { setPendingAction(null); setPassword(''); setError(''); }}
                  className="px-4 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors cursor-pointer"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={isLoading}
                  className="px-4 py-2 text-xs font-bold text-white bg-[#0058be] rounded-lg hover:bg-[#004a9f] transition-colors disabled:opacity-70 flex items-center gap-1 cursor-pointer"
                >
                  {isLoading && <span className="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>}
                  확인
                </button>
              </div>
            </form>
          </div>
          </div>
        )}
      </div>
    </div>
  );
}
