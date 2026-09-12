import React, { useState, useRef, useEffect } from 'react';
import useUserStore from '../../store/useUserStore';
import useDroneStore from '../../store/useDroneStore';
import { uploadProfileImage, resetProfileImage, updateMyInfo, deleteMyAccount } from '../../services/api';
import Avatar from '../common/Avatar';
import toast from 'react-hot-toast';
import { parseServerTime } from '../../utils/time';

/**
 * 「내 계정」 탭 - 내 정보와 내 프로필 수정만 담는다.
 *
 * 남의 계정을 관리하는 일은 UserAdminTab 이 맡는다. 예전에는 한 파일에
 * 둘이 섞여 있어, VIEWER가 스크롤하면 쓸 수 없는 관리자 표가 딸려 나왔다.
 */
/** 가입 일시. 표·판단 창과 같은 형식(YY.MM.DD HH:MM)으로 맞춘다. */
const fmtDate = (v) => {
  if (!v) return '-';
  try {
    return parseServerTime(v).toLocaleString('ko-KR', {
      year: '2-digit', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    });
  } catch {
    return String(v);
  }
};

/** 계정 상태 표기. 서버 값(APPROVED/PENDING/REJECTED)을 그대로 보여주면 읽기 어렵다. */
const STATUS_LABEL = {
  APPROVED: '승인',
  PENDING: '승인 대기',
  REJECTED: '반려',
  DISABLED: '보류',
};

const STATUS_STYLE = {
  APPROVED: 'bg-green-100 text-green-700',
  PENDING: 'bg-yellow-100 text-yellow-700 border border-yellow-200',
  REJECTED: 'bg-red-100 text-red-700',
};

export default function MyAccountTab({ requireVerify }) {
  const { userInfo, setUserInfo } = useUserStore();
  const setHasUnsavedChanges = useDroneStore((state) => state.setHasUnsavedChanges);

  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [deleteTyped, setDeleteTyped] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);

  const [isEditingMyProfile, setIsEditingMyProfile] = useState(false);
  const [showMyPassword, setShowMyPassword] = useState(false);
  const [myProfileForm, setMyProfileForm] = useState({ name: '', email: '', pwd: '' });

  // 수정 폼이 열려 있는 동안에만 "작성 중" 경고를 켠다.
  useEffect(() => {
    setHasUnsavedChanges(isEditingMyProfile);
  }, [isEditingMyProfile, setHasUnsavedChanges]);

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
      toast.error(err.userMessage ?? '프로필 사진 변경에 실패했습니다.');
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
    } catch (err) {
      toast.error(err.userMessage ?? '기본 프로필 변경에 실패했습니다.');
    } finally {
      setIsUploading(false);
    }
  };

  // 이름/이메일/비밀번호를 바꾸는 자리다. 여기서만 재확인을 받는다.
  // 사진 교체는 계정 정보가 아니므로 막지 않는다 - 매번 비밀번호를 묻게 하면
  // 사진 한 장 바꾸는 데도 입력해야 한다.
  const handleEditMyProfileClick = () => requireVerify(() => {
    setMyProfileForm({ name: userInfo?.name || '', email: userInfo?.email || '', pwd: '' });
    setShowMyPassword(false);
    setIsEditingMyProfile(true);
  });

  const handleCancelMyProfile = () => {
    setIsEditingMyProfile(false);
    setMyProfileForm({ name: '', email: '', pwd: '' });
    setShowMyPassword(false);
  };

  const handleSaveMyProfile = async () => {
    try {
      setIsLoading(true);
      await updateMyInfo(myProfileForm);
      toast.success('내 프로필이 수정되었습니다.');
      setUserInfo({
        ...userInfo,
        name: myProfileForm.name || userInfo.name,
        email: myProfileForm.email || userInfo.email,
      });
      setIsEditingMyProfile(false);
    } catch (err) {
      toast.error(err.userMessage ?? '프로필 수정 중 오류가 발생했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  // 되돌릴 수 없는 조작이다. 재확인을 통과한 뒤에도 아이디를 직접 적게 해서
  // 습관적으로 눌러 넘어가는 것을 막는다. 브라우저 기본 창(prompt)은 모양이
  // 깨지고 경고의 무게가 전달되지 않아 비상 정지 모달과 같은 양식으로 띄운다.
  const handleDeleteMyAccount = () => requireVerify(() => {
    setDeleteTyped('');
    setIsDeleteOpen(true);
  });

  const runDeleteMyAccount = async () => {
    setIsDeleting(true);
    try {
      await deleteMyAccount();
      toast.success('계정이 삭제되었습니다.');
      // 세션이 끊겼으므로 새로 시작한다 - 남은 화면이 계속 인증된 척하면 안 된다.
      window.location.reload();
    } catch (err) {
      toast.error(err.userMessage ?? '계정 삭제에 실패했습니다.');
      setIsDeleting(false);
    }
  };

  return (
    <>
      {/* 내 정보 - 위는 사람(사진/이름), 아래는 값(라벨/값 2열)으로 나눈다.
          예전에는 파란 상자 하나에 아바타와 밑줄 링크가 몰려 있어 무엇이
          누를 수 있는 것인지 구분되지 않았다. */}
      <div className="rounded-xl border border-gray-200 overflow-hidden">
        <div className="p-5 flex items-center gap-5">
          {/* 사진을 눌러 바로 교체할 수 있게 한다 */}
          <div className="relative group shrink-0">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              title="프로필 사진 변경"
              className="block rounded-full transition-all duration-150 hover:ring-2 hover:ring-blue-300 active:scale-95 disabled:opacity-50 cursor-pointer"
            >
              <Avatar src={userInfo?.profileImage} userId={userInfo?.userId} size={72} />
              <span className="absolute inset-0 rounded-full bg-black/45 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                <span className="material-symbols-outlined text-[22px]">photo_camera</span>
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

          <div className="min-w-0 flex-1">
            {/* 보기와 편집의 높이를 같게 맞춘다. 입력칸이 글자보다 크면
                카드가 늘어나 아래 내용이 밀린다. */}
            <div className="h-9 flex items-center gap-2">
              {isEditingMyProfile ? (
                <input
                  type="text"
                  value={myProfileForm.name}
                  onChange={(e) => setMyProfileForm({ ...myProfileForm, name: e.target.value })}
                  placeholder="이름"
                  className="min-w-0 flex-1 px-3 py-1 font-bold text-gray-900 text-lg border border-gray-200 rounded-lg outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]"
                />
              ) : (
                <p className="font-bold text-gray-900 text-xl truncate">{userInfo?.name}</p>
              )}
              {/* 2) 권한을 이름 옆으로. 아이디는 아래 데이터 칸으로 내렸다. */}
              <span className="shrink-0 px-2 py-0.5 rounded-full bg-[#e5eeff] text-[#0058be] text-xs font-bold">
                {userInfo?.role}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="px-2.5 py-1.5 text-[11px] font-bold text-gray-700 bg-gray-100 border border-gray-200 rounded-lg hover:bg-gray-200 transition-colors duration-150 disabled:opacity-50 cursor-pointer"
              >
                {isUploading ? '업로드 중…' : '사진 변경'}
              </button>
              {userInfo?.profileImage && (
                <button
                  onClick={handleProfileImageReset}
                  disabled={isUploading}
                  className="px-2.5 py-1.5 text-[11px] font-bold text-gray-500 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors duration-150 disabled:opacity-50 cursor-pointer"
                >
                  기본으로
                </button>
              )}
            </div>
          </div>
        </div>

        <dl className="border-t border-gray-100 divide-y divide-gray-100 text-sm">
          <div className="flex px-5 py-3 items-center">
            <dt className="w-24 shrink-0 text-xs font-bold text-gray-400">아이디</dt>
            <dd className="flex-1 min-w-0 h-9 flex items-center text-gray-800 break-all">{userInfo?.userId}</dd>
          </div>
          <div className="flex px-5 py-3 items-center">
            <dt className="w-24 shrink-0 text-xs font-bold text-gray-400">이메일</dt>
            <dd className="flex-1 min-w-0 h-9 flex items-center">
              {isEditingMyProfile ? (
                <input
                  type="email"
                  value={myProfileForm.email}
                  onChange={(e) => setMyProfileForm({ ...myProfileForm, email: e.target.value })}
                  placeholder="이메일"
                  className="w-full px-3 py-1 text-sm border border-gray-200 rounded-lg outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]"
                />
              ) : (
                <span className="text-gray-800 break-all">{userInfo?.email || '-'}</span>
              )}
            </dd>
          </div>
          <div className="flex px-5 py-3">
            <dt className="w-24 shrink-0 text-xs font-bold text-gray-400 pt-0.5">계정 상태</dt>
            <dd>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${STATUS_STYLE[userInfo?.status] ?? 'bg-gray-100 text-gray-600'}`}>
                {STATUS_LABEL[userInfo?.status] ?? (userInfo?.status || '-')}
              </span>
            </dd>
          </div>
          {/* 비밀번호는 평소 보여줄 값이 없다. 수정 중에만 자리를 만든다. */}
          {isEditingMyProfile && (
            <div className="flex px-5 py-3">
              <dt className="w-24 shrink-0 text-xs font-bold text-gray-400 pt-2">새 비밀번호</dt>
              <dd className="flex-1 min-w-0">
                <div className="relative flex items-center">
                  <input
                    type={showMyPassword ? 'text' : 'password'}
                    value={myProfileForm.pwd}
                    onChange={(e) => setMyProfileForm({ ...myProfileForm, pwd: e.target.value })}
                    placeholder="변경 시에만 입력"
                    autoComplete="new-password"
                    className="w-full px-3 py-1.5 pr-10 text-sm border border-gray-200 rounded-lg outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]"
                  />
                  {myProfileForm.pwd.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowMyPassword(!showMyPassword)}
                      className="absolute right-2 text-gray-500 hover:text-gray-800 p-1 rounded-md hover:bg-gray-100 transition-colors cursor-pointer"
                    >
                      {/* index.css가 .material-symbols-outlined에 FILL·wght를 한 선언으로
                          걸어두므로, 인라인으로 덮을 때 둘을 함께 지정해야 한다. */}
                      <span
                        className="material-symbols-outlined text-[18px]"
                        style={{ fontVariationSettings: "'FILL' 0, 'wght' 200" }}
                      >
                        {showMyPassword ? 'visibility_off' : 'visibility'}
                      </span>
                    </button>
                  )}
                </div>
              </dd>
            </div>
          )}

          <div className="flex px-5 py-3 items-center">
            <dt className="w-24 shrink-0 text-xs font-bold text-gray-400">가입 일시</dt>
            <dd className="flex-1 min-w-0 h-9 flex items-center text-gray-800">
              {fmtDate(userInfo?.createdAt)}
            </dd>
          </div>
        </dl>

      </div>

      {/* 내 계정에 대한 조작을 한 줄에 모은다 */}
      {/* 수정 중에는 계정 삭제를 감춘다. 고치는 중에 지우는 버튼이 옆에
          있으면 오조작을 부른다. */}
      <div className="mt-auto pt-4 border-t border-gray-100 flex justify-end gap-2">
        {isEditingMyProfile ? (
          <>
            <button
              onClick={handleCancelMyProfile}
              className="px-3 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors duration-150 cursor-pointer"
            >
              취소
            </button>
            <button
              onClick={handleSaveMyProfile}
              disabled={isLoading}
              className="px-3 py-2 text-xs font-bold text-white bg-[#0058be] rounded-lg hover:bg-[#004a9f] transition-colors duration-150 disabled:opacity-70 flex items-center gap-1 cursor-pointer"
            >
              {isLoading
                ? <span className="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>
                : <span className="material-symbols-outlined text-[16px]">save</span>}
              저장
            </button>
          </>
        ) : (
          <>
            <button
              onClick={handleEditMyProfileClick}
              className="px-3 py-2 text-xs font-bold text-white bg-[#0058be] rounded-lg hover:bg-[#004a9f] transition-colors duration-150 flex items-center gap-1 cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">edit</span>
              프로필 수정
            </button>
            <button
              onClick={handleDeleteMyAccount}
              className="px-3 py-2 text-xs font-bold text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors duration-150 flex items-center gap-1 cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">person_remove</span>
              계정 삭제
            </button>
          </>
        )}
      </div>

      {/* 계정 삭제 확인 - 비상 정지 모달과 같은 양식.
          되돌릴 수 없는 조작이므로 무게를 그림과 색으로 전달한다. */}
      {isDeleteOpen && (
        <div className="absolute inset-0 z-[255] flex items-center justify-center bg-black/40 backdrop-blur-sm rounded-xl">
          <div className="bg-white w-full max-w-sm rounded-2xl shadow-2xl p-6 relative animate-in fade-in zoom-in-95 duration-200">
            <button
              type="button"
              onClick={() => setIsDeleteOpen(false)}
              aria-label="닫기"
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
            >
              <span className="material-symbols-outlined">close</span>
            </button>

            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-red-100 text-red-600 rounded-full flex items-center justify-center">
                <span className="material-symbols-outlined">person_remove</span>
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">계정 제거</h2>
                <p className="text-xs text-gray-500 font-medium">{userInfo?.userId}</p>
              </div>
            </div>

            <hr className="my-4 border-gray-200" />

            <p className="text-sm text-gray-700 mb-4 leading-relaxed">
              이 계정과 계정에 남은 기록이 <span className="font-bold">영구히</span> 삭제됩니다.
              <span className="text-red-500 font-bold bg-red-50 px-1 mt-1 inline-block">되돌릴 수 없습니다.</span>
            </p>

            <label className="block text-xs font-bold text-gray-500 mb-1">
              계속하려면 아이디 <span className="text-gray-900">{userInfo?.userId}</span> 를 입력하세요
            </label>
            <input
              type="text"
              value={deleteTyped}
              onChange={(e) => setDeleteTyped(e.target.value)}
              autoFocus
              autoComplete="off"
              placeholder={userInfo?.userId}
              className="w-full px-3 py-2 mb-5 text-sm border border-gray-300 rounded-lg outline-none transition-all focus:ring-2 focus:ring-red-100 focus:border-red-400"
            />

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setIsDeleteOpen(false)}
                className="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-50 border border-gray-200 hover:bg-gray-100 transition-colors cursor-pointer"
              >
                뒤로가기
              </button>
              <button
                onClick={runDeleteMyAccount}
                disabled={deleteTyped.trim() !== userInfo?.userId || isDeleting}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700 shadow-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1"
              >
                {isDeleting && <span className="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>}
                제거
              </button>
            </div>
          </div>
        </div>
      )}

    </>
  );
}
