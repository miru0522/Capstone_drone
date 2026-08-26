import React, { useState, useEffect, useRef, useMemo } from 'react';
import useUserStore from '../../store/useUserStore';
import useDroneStore from '../../store/useDroneStore';
import { verifyPassword, getAdminUsers, approveUser, rejectUser, changeUserRole, deleteUserByAdmin, changeUserPasswordByAdmin, uploadProfileImage, resetProfileImage, updateMyInfo, updateUserByAdmin } from '../../services/api';
import Avatar from '../common/Avatar';
import toast from 'react-hot-toast';

export default function AccountManagementModal() {
  const { isAccountModalOpen, closeAccountModal, userInfo, setUserInfo } = useUserStore();
  const setHasUnsavedChanges = useDroneStore((state) => state.setHasUnsavedChanges);
  const [isVerified, setIsVerified] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // 내 프로필 수정
  const [isEditingMyProfile, setIsEditingMyProfile] = useState(false);
  const [showMyPassword, setShowMyPassword] = useState(false);
  const [myProfileForm, setMyProfileForm] = useState({ name: '', email: '', pwd: '' });

  // 관리자 전용 타 유저 수정
  const [editingAdminUserId, setEditingAdminUserId] = useState(null);
  const [showAdminPassword, setShowAdminPassword] = useState(false);
  const [adminProfileForm, setAdminProfileForm] = useState({ name: '', email: '', pwd: '' });

  // 폼이 열렸을 때만 UnsavedChanges 활성화
  useEffect(() => {
    if (isEditingMyProfile || editingAdminUserId) {
      setHasUnsavedChanges(true);
    } else {
      setHasUnsavedChanges(false);
    }
  }, [isEditingMyProfile, editingAdminUserId, setHasUnsavedChanges]);

  // 프로필 사진 변경
  const fileInputRef = useRef(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleProfileImageChange = async (e) => {
    const file = e.target.files?.[0];
    // 같은 파일을 다시 골라도 onChange가 걸리도록 값을 비워둔다
    e.target.value = '';
    if (!file) return;

    setIsUploading(true);
    try {
      const res = await uploadProfileImage(file);
      setUserInfo({ ...userInfo, profileImage: res.profileImage });
      toast.success('프로필 사진이 변경되었습니다.');
    } catch (err) {
      toast.error(err?.response?.data?.message || '프로필 사진 변경에 실패했습니다.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleProfileImageReset = async () => {
    setIsUploading(true);
    try {
      await resetProfileImage();
      setUserInfo({ ...userInfo, profileImage: null });
      toast.success('기본 프로필로 변경되었습니다.');
    } catch {
      toast.error('기본 프로필 변경에 실패했습니다.');
    } finally {
      setIsUploading(false);
    }
  };
  
  // 관리자 전용 상태
  const [users, setUsers] = useState([]);
  const isAdmin = userInfo?.role === 'ADMIN';

  // 본인 계정을 맨 위로 올린다. 나머지 순서는 서버가 준 그대로 둔다.
  // (id가 응답마다 있으리라 보장이 없어 로그인 아이디로 대조한다)
  const sortedUsers = useMemo(() => {
    if (!Array.isArray(users)) return [];
    const me = userInfo?.userId;
    if (!me) return users;
    return [...users].sort((a, b) => (b.userId === me) - (a.userId === me));
  }, [users, userInfo?.userId]);

  console.log("=== [DEBUG] AccountManagementModal 렌더링됨. 현재 userInfo: ===", userInfo);

  useEffect(() => {
    if (isAccountModalOpen && !isVerified) {
      setPassword('');
      setError('');
    }
    // 창 닫힐 때 인증 초기화 (보안 유지)
    if (!isAccountModalOpen) {
      setIsVerified(false);
    }
  }, [isAccountModalOpen, isVerified]);

  useEffect(() => {
    if (isVerified && isAdmin) {
      fetchUsers();
    }
  }, [isVerified, isAdmin]);

  const fetchUsers = async () => {
    try {
      setIsLoading(true);
      const data = await getAdminUsers();
      setUsers(data);
    } catch (e) {
      console.error(e);
      setError('사용자 목록을 불러오는 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      await verifyPassword(password);
      setIsVerified(true);
    } catch (err) {
      setError('비밀번호가 일치하지 않습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleApprove = async (id) => {
    if (!window.confirm('이 사용자의 가입을 승인하시겠습니까?')) return;
    try {
      await approveUser(id);
      fetchUsers();
    } catch (e) {
      alert('승인 처리 중 오류가 발생했습니다.');
    }
  };

  const handleReject = async (id) => {
    if (!window.confirm('이 사용자의 가입을 거절하시겠습니까?')) return;
    try {
      await rejectUser(id);
      fetchUsers();
    } catch (e) {
      alert('거절 처리 중 오류가 발생했습니다.');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('경고: 이 사용자의 계정을 영구 삭제하시겠습니까?\n삭제된 계정은 복구할 수 없습니다.')) return;
    try {
      await deleteUserByAdmin(id);
      fetchUsers();
    } catch (e) {
      alert('삭제 처리 중 오류가 발생했습니다.');
    }
  };

  const handleRoleChange = async (id, newRole) => {
    if (!window.confirm(`권한을 ${newRole}(으)로 변경하시겠습니까?`)) return;
    try {
      await changeUserRole(id, newRole);
      fetchUsers();
    } catch (e) {
      alert('권한 변경 중 오류가 발생했습니다.');
    }
  };

  const handlePasswordChange = async (id) => {
    const newPassword = window.prompt('해당 사용자의 새로운 비밀번호를 입력해주세요.');
    if (!newPassword || newPassword.trim() === '') return;
    
    if (!window.confirm(`비밀번호를 강제 변경하시겠습니까?`)) return;
    try {
      await changeUserPasswordByAdmin(id, newPassword);
      alert('비밀번호가 성공적으로 변경되었습니다.');
    } catch (e) {
      alert('비밀번호 변경 중 오류가 발생했습니다.');
    }
  };

  const handleEditMyProfileClick = () => {
    setMyProfileForm({ name: userInfo?.name || '', email: userInfo?.email || '', pwd: '' });
    setShowMyPassword(false);
    setIsEditingMyProfile(true);
  };

  const handleSaveMyProfile = async () => {
    try {
      setIsLoading(true);
      await updateMyInfo(myProfileForm);
      toast.success('내 프로필이 성공적으로 수정되었습니다.');
      setUserInfo({ ...userInfo, name: myProfileForm.name || userInfo.name, email: myProfileForm.email || userInfo.email });
      setIsEditingMyProfile(false);
    } catch (e) {
      toast.error('프로필 수정 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAdminEditProfileClick = (user) => {
    setEditingAdminUserId(user.id);
    setShowAdminPassword(false);
    setAdminProfileForm({
      name: user.name || '',
      email: user.email || '',
      pwd: ''
    });
  };

  const handleAdminSaveProfile = async (id) => {
    try {
      await updateUserByAdmin(id, adminProfileForm);
      toast.success('사용자 프로필이 수정되었습니다.');
      setEditingAdminUserId(null);
      fetchUsers();
    } catch (e) {
      toast.error('사용자 프로필 수정 중 오류가 발생했습니다.');
    }
  };

  if (!isAccountModalOpen) return null;

  return (
    <div className="absolute inset-0 z-[200] flex items-center justify-center bg-[#0b1c30] bg-opacity-80 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl p-6 relative w-full max-w-2xl animate-in fade-in zoom-in duration-200">
        <button 
          onClick={() => {
            setHasUnsavedChanges(false);
            closeAccountModal();
          }}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined">close</span>
        </button>

        <h2 className="text-xl font-black tracking-tight text-gray-900 flex items-center gap-2 mb-6 border-b pb-4">
          <span className="material-symbols-outlined text-[#0058be]">manage_accounts</span>
          {isVerified ? '계정 및 승인 관리' : '비밀번호 확인'}
        </h2>

        {!isVerified ? (
          <div className="px-8 py-4 max-w-sm mx-auto">
            <p className="text-sm text-gray-600 mb-6 text-center">
              계정 설정 및 관리자 메뉴에 접근하려면<br />현재 계정의 비밀번호를 다시 한 번 입력해주세요.
            </p>
            <form onSubmit={handleVerify} className="space-y-4">
              <div>
                <input 
                  type="password" 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#0058be] outline-none text-center tracking-widest"
                  placeholder="비밀번호"
                  required
                />
              </div>
              {error && <p className="text-red-500 text-sm text-center font-bold">{error}</p>}
              <button 
                type="submit" 
                disabled={isLoading}
                className="w-full py-2 bg-[#0058be] hover:bg-[#004a9f] text-white font-bold rounded-lg transition-colors flex justify-center items-center h-10"
              >
                {isLoading ? <span className="material-symbols-outlined animate-spin">progress_activity</span> : '확인'}
              </button>
            </form>
          </div>
        ) : (
          <div className="flex flex-col h-[500px]">
            {/* 내 정보 요약 영역 */}
            <div className="bg-blue-50 p-4 rounded-lg mb-4 flex justify-between items-center border border-blue-100">
              <div className="flex items-center gap-4">
                {/* 사진을 눌러 바로 교체할 수 있게 한다 */}
                <div className="relative group shrink-0">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploading}
                    title="프로필 사진 변경"
                    className="block rounded-full transition-all hover:ring-2 hover:ring-blue-300 active:scale-95 disabled:opacity-50"
                  >
                    <Avatar src={userInfo?.profileImage} userId={userInfo?.userId} size={56} />
                    <span className="absolute inset-0 rounded-full bg-black/45 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                      <span className="material-symbols-outlined text-[20px]">photo_camera</span>
                    </span>
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleProfileImageChange}
                  />
                </div>
                <div>
                  <p className="text-xs font-bold text-blue-500 mb-1">내 정보</p>
                  <p className="font-bold text-gray-800 text-lg">{userInfo?.name} <span className="text-sm font-normal text-gray-500">({userInfo?.userId})</span></p>
                  <div className="flex items-center gap-2 mt-1">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploading}
                      className="text-[11px] font-bold text-blue-600 hover:underline disabled:opacity-50"
                    >
                      {isUploading ? '업로드 중…' : '사진 변경'}
                    </button>
                    {userInfo?.profileImage && (
                      <>
                        <span className="text-[11px] text-gray-300">|</span>
                        <button
                          onClick={handleProfileImageReset}
                          disabled={isUploading}
                          className="text-[11px] font-bold text-gray-500 hover:underline disabled:opacity-50"
                        >
                          기본으로
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <div className="px-3 py-1 bg-white border border-blue-200 rounded-full text-xs font-bold text-blue-700">
                  {userInfo?.role}
                </div>
                {!isEditingMyProfile && (
                  <button
                    onClick={handleEditMyProfileClick}
                    className="text-xs font-bold text-[#0058be] hover:underline"
                  >
                    프로필 수정
                  </button>
                )}
              </div>
            </div>

            {/* 관리자 승인 대기 목록 (ADMIN 전용) */}
            {isAdmin && (
              <div className="flex-1 flex flex-col overflow-hidden">
                <h3 className="font-bold text-gray-800 mb-3 flex justify-between items-center">
                  <span>사용자 관리</span>
                  <button onClick={fetchUsers} className="text-xs text-[#0058be] hover:underline flex items-center gap-1">
                    <span className="material-symbols-outlined text-[14px]">refresh</span>새로고침
                  </button>
                </h3>
                <div className="overflow-y-auto overflow-x-hidden flex-1 bg-gray-50 rounded-lg border border-gray-200">
                  <table className="w-full text-sm text-center">
                    <thead className="bg-gray-100 sticky top-0 text-xs uppercase font-bold text-gray-600">
                      <tr>
                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">아이디</th>
                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">이름</th>
                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">권한</th>
                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">상태</th>
                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">관리</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedUsers.length === 0 ? (
                        <tr>
                          <td colSpan="5" className="text-center py-8 text-gray-500 font-medium">사용자가 없습니다.</td>
                        </tr>
                      ) : (
                        sortedUsers.map(u => {
                          const isMe = u.userId === userInfo?.userId;
                          return (
                          <React.Fragment key={u.id}>
                            <tr className={`border-b transition-colors ${
                              isMe
                                ? 'bg-[#e5eeff] border-l-4 border-l-[#0058be] hover:bg-[#dae2fd]'
                                : 'bg-white hover:bg-blue-50/50'
                            }`}>
                              <td className="px-2 py-3 font-medium text-gray-900 break-all">
                                <span className="inline-flex items-center gap-1.5">
                                  {u.userId}
                                  {isMe && (
                                    <span className="px-1.5 py-0.5 rounded bg-[#0058be] text-white text-[10px] font-bold tracking-wide">
                                      나
                                    </span>
                                  )}
                                </span>
                              </td>
                              <td className="px-2 py-3 break-all">{u.name}</td>
                              <td className="px-2 py-3 whitespace-nowrap">
                                {/* 승인된 계정만 권한을 바꿀 수 있다. 다만 바꿀 수 없는 행의 배지가
                                    작으면 열이 들쭉날쭉해 보이므로, 같은 크기의 박스를 유지하고
                                    '조작 불가'만 점선·흐린 색으로 나타낸다. */}
                                {u.status === 'APPROVED' ? (
                                  /* 본인은 강등할 수 없다. 유일한 ADMIN이 자기를 내리면
                                     관리자 기능에 아무도 접근할 수 없게 된다. */
                                  <select
                                    value={u.role}
                                    onChange={(e) => handleRoleChange(u.id, e.target.value)}
                                    disabled={isMe}
                                    title={isMe ? '본인 권한은 변경할 수 없습니다' : undefined}
                                    className={`w-[92px] px-1.5 py-1 rounded text-xs font-bold outline-none border ${isMe ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'} ${u.role === 'ADMIN' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-gray-50 border-gray-200 text-gray-700'}`}
                                  >
                                    <option value="ADMIN">ADMIN</option>
                                    <option value="OPERATOR">OPERATOR</option>
                                    <option value="VIEWER">VIEWER</option>
                                  </select>
                                ) : (
                                  <span
                                    className="inline-block w-[92px] px-1.5 py-1 rounded text-xs font-bold text-left border border-dashed border-gray-300 bg-gray-50 text-gray-400"
                                    title="승인된 계정만 권한을 변경할 수 있습니다"
                                  >
                                    {u.role}
                                  </span>
                                )}
                              </td>
                              <td className="px-2 py-3 whitespace-nowrap">
                                <span className={`px-2 py-0.5 rounded-full text-xs font-bold 
                                  ${u.status === 'PENDING' ? 'bg-yellow-100 text-yellow-700 border border-yellow-200' : 
                                    u.status === 'APPROVED' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}
                                >
                                  {u.status}
                                </span>
                              </td>
                              <td className="px-2 py-3 text-center whitespace-nowrap">
                                {u.status === 'PENDING' ? (
                                  <div className="flex justify-center gap-1.5">
                                    <button onClick={() => handleApprove(u.id)} className="px-2 py-1 bg-[#0058be] text-white text-xs font-bold rounded hover:bg-[#004a9f]">승인</button>
                                    <button onClick={() => handleReject(u.id)} className="px-2 py-1 bg-red-500 text-white text-xs font-bold rounded hover:bg-red-600">거절</button>
                                  </div>
                                ) : u.status === 'APPROVED' ? (
                                  <div className="flex justify-center gap-1.5">
                                    <button onClick={() => handleAdminEditProfileClick(u)} className="px-1.5 py-1 bg-gray-200 text-gray-700 text-xs font-bold rounded hover:bg-gray-300 whitespace-nowrap">프로필 수정</button>
                                    {/* 본인 계정은 여기서 지울 수 없다. 지우려면 '내 정보'의 계정 삭제를 쓴다. */}
                                    {!isMe && (
                                      <button onClick={() => handleDelete(u.id)} className="px-2 py-1 bg-red-50 text-red-600 border border-red-200 text-xs font-bold rounded hover:bg-red-100">삭제</button>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-xs text-gray-400">-</span>
                                )}
                              </td>
                            </tr>
                          </React.Fragment>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 내 프로필 수정 레이어 팝업 — 관리자 프로필 수정 팝업과 같은 형태로 맞췄다 */}
      {isEditingMyProfile && (
        <div className="absolute inset-0 z-[250] flex items-center justify-center bg-black/40 backdrop-blur-sm rounded-xl">
          <div className="bg-white p-6 rounded-xl shadow-2xl border border-blue-100 w-[400px] animate-in fade-in zoom-in duration-200">
            <div className="flex items-center gap-2 mb-4 border-b pb-3">
              <span className="material-symbols-outlined text-[#0058be] text-[20px]">edit_square</span>
              <span className="text-sm font-bold text-gray-800">내 프로필 수정</span>
            </div>
            <div className="flex flex-col gap-4 text-left">
              <div className="relative">
                <label className="block text-xs font-bold text-gray-500 mb-1">이름</label>
                <div className="relative flex items-center">
                  <span className="material-symbols-outlined absolute left-3 text-gray-400 text-[18px] pointer-events-none">person</span>
                  <input
                    type="text"
                    value={myProfileForm.name}
                    onChange={(e) => setMyProfileForm({ ...myProfileForm, name: e.target.value })}
                    className="w-full pl-10 pr-3 py-2 border border-gray-200 rounded-lg text-sm outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]"
                  />
                </div>
              </div>

              <div className="relative">
                <label className="block text-xs font-bold text-gray-500 mb-1">이메일</label>
                <div className="relative flex items-center">
                  <span className="material-symbols-outlined absolute left-3 text-gray-400 text-[18px] pointer-events-none">mail</span>
                  <input
                    type="email"
                    value={myProfileForm.email}
                    onChange={(e) => setMyProfileForm({ ...myProfileForm, email: e.target.value })}
                    className="w-full pl-10 pr-3 py-2 border border-gray-200 rounded-lg text-sm outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]"
                  />
                </div>
              </div>

              <div className="relative">
                <label className="block text-xs font-bold text-gray-500 mb-1">새 비밀번호</label>
                <div className="relative flex items-center">
                  <span className="material-symbols-outlined absolute left-3 text-gray-400 text-[18px] pointer-events-none">key</span>
                  <input
                    type={showMyPassword ? 'text' : 'password'}
                    value={myProfileForm.pwd}
                    onChange={(e) => setMyProfileForm({ ...myProfileForm, pwd: e.target.value })}
                    placeholder="새 비밀번호 (변경 시에만 입력)"
                    autoComplete="new-password"
                    className="w-full pl-10 pr-10 py-2 border border-gray-200 rounded-lg text-sm outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]"
                  />
                  {myProfileForm.pwd.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowMyPassword(!showMyPassword)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-800 focus:outline-none flex items-center justify-center p-1 rounded-md hover:bg-gray-100 transition-colors"
                    >
                      {/* 얇은 선(wght 200). index.css가 .material-symbols-outlined에
                          FILL·wght·GRAD·opsz를 한 선언으로 걸어두므로, 인라인으로 덮어쓸 때
                          wght만 적으면 FILL이 기본값으로 돌아간다. 함께 지정한다. */}
                      <span
                        className="material-symbols-outlined text-[18px]"
                        style={{ fontVariationSettings: "'FILL' 0, 'wght' 200" }}
                      >
                        {showMyPassword ? 'visibility_off' : 'visibility'}
                      </span>
                    </button>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => { setIsEditingMyProfile(false); setMyProfileForm({ name: '', email: '', pwd: '' }); setShowMyPassword(false); }}
                  className="px-4 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  취소
                </button>
                <button
                  onClick={handleSaveMyProfile}
                  disabled={isLoading}
                  className="flex items-center gap-1 px-4 py-2 text-xs font-bold text-white bg-gradient-to-r from-[#0058be] to-[#004a9f] rounded-lg hover:shadow-md transition-all disabled:opacity-70"
                >
                  {isLoading ? <span className="material-symbols-outlined animate-spin text-[16px]">progress_activity</span> : <span className="material-symbols-outlined text-[16px]">save</span>}
                  {isLoading ? '저장 중...' : '저장 완료'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 관리자 프로필 수정 레이어 팝업 */}
      {editingAdminUserId && (
        <div className="absolute inset-0 z-[250] flex items-center justify-center bg-black/40 backdrop-blur-sm rounded-xl">
          <div className="bg-white p-6 rounded-xl shadow-2xl border border-blue-100 w-[400px] animate-in fade-in zoom-in duration-200">
            <div className="flex items-center gap-2 mb-4 border-b pb-3">
              <span className="material-symbols-outlined text-blue-500 text-[20px]">manage_accounts</span>
              <span className="text-sm font-bold text-gray-800">사용자 프로필 수정</span>
            </div>
            <div className="flex flex-col gap-4 text-left">
              <div className="w-full">
                <label className="block text-xs font-bold text-gray-500 mb-1">이름</label>
                <div className="relative flex items-center">
                  <span className="material-symbols-outlined absolute left-3 text-gray-400 text-[18px] pointer-events-none">person</span>
                  <input type="text" value={adminProfileForm.name} onChange={e => setAdminProfileForm({...adminProfileForm, name: e.target.value})} className="w-full pl-10 pr-3 py-2 text-sm border border-gray-200 rounded-lg outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]" />
                </div>
              </div>
              <div className="w-full">
                <label className="block text-xs font-bold text-gray-500 mb-1">이메일</label>
                <div className="relative flex items-center">
                  <span className="material-symbols-outlined absolute left-3 text-gray-400 text-[18px] pointer-events-none">mail</span>
                  <input type="email" value={adminProfileForm.email} onChange={e => setAdminProfileForm({...adminProfileForm, email: e.target.value})} className="w-full pl-10 pr-3 py-2 text-sm border border-gray-200 rounded-lg outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]" />
                </div>
              </div>
              <div className="w-full">
                <label className="block text-xs font-bold text-gray-500 mb-1">새 비밀번호</label>
                <div className="relative flex items-center">
                  <span className="material-symbols-outlined absolute left-3 text-gray-400 text-[18px] pointer-events-none">key</span>
                  <input 
                    type={showAdminPassword ? 'text' : 'password'} 
                    placeholder="새 비밀번호 (선택)"
                    value={adminProfileForm.pwd} 
                    onChange={e => setAdminProfileForm({...adminProfileForm, pwd: e.target.value})} 
                    autoComplete="new-password"
                    className="w-full pl-10 pr-10 py-2 text-sm border border-gray-200 rounded-lg outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]" 
                  />
                  {adminProfileForm.pwd.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowAdminPassword(!showAdminPassword)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-800 focus:outline-none flex items-center justify-center p-1 rounded-md hover:bg-gray-100 transition-colors"
                    >
                      <span
                        className="material-symbols-outlined text-[18px]"
                        style={{ fontVariationSettings: "'FILL' 0, 'wght' 200" }}
                      >
                        {showAdminPassword ? 'visibility_off' : 'visibility'}
                      </span>
                    </button>
                  )}
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-2 pt-2 border-t border-gray-50">
                <button onClick={() => { setEditingAdminUserId(null); setShowAdminPassword(false); }} className="px-4 py-2 bg-gray-100 text-gray-600 text-xs font-bold rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-1">
                  취소
                </button>
                <button onClick={() => handleAdminSaveProfile(editingAdminUserId)} className="px-4 py-2 bg-gradient-to-r from-[#0058be] to-[#004a9f] text-white text-xs font-bold rounded-lg hover:shadow-md hover:scale-105 transition-all flex items-center gap-1">
                  저장
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
