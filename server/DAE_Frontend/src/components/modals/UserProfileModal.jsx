import React, { useState } from 'react';
import { updateUserByAdmin, approveUser, disableUser } from '../../services/api';
import Avatar from '../common/Avatar';
import toast from 'react-hot-toast';
import { parseServerTime } from '../../utils/time';

/**
 * 한 사용자의 프로필 관리 창 (ADMIN 전용).
 *
 * 「내 계정」의 내 정보 카드와 같은 모양이다 — 위는 사람(사진·이름), 아래는
 * 라벨/값 2열. 다만 여기서는 값이 처음부터 입력칸이고 <b>계정 상태까지</b>
 * 바꿀 수 있다.
 *
 * 표의 「관리」 하나로 열린다. <b>첫 진입은 조회만</b>이고, 「편집」을 눌러야
 * 고칠 수 있다. 보러 열었을 때 입력칸이 바로 떠 있으면 실수로 값을 건드린다.
 * 비밀번호 재확인도 그 「편집」에서 받는다 - 보기만 할 때는 묻지 않는다.
 *
 * ⚠️ 상태 변경은 별도 API다(approve/reject). 프로필 저장 API는 이름·이메일·
 *    비밀번호만 받는다. 그래서 저장할 때 두 번 부르되, <b>상태가 실제로
 *    바뀌었을 때만</b> 두 번째를 부른다.
 *
 * PENDING(승인 대기)으로 되돌리는 API는 없고, 만들지 않기로 했다 —
 * 「승인 대기」는 "관리자가 아직 보지 않았다"는 뜻이라 되돌릴 이유가 없다.
 */

/** 화면에 보여줄 상태 이름. 서버 값(APPROVED/REJECTED)은 읽기 어렵다. */
const STATUS_LABEL = {
  APPROVED: '승인',
  PENDING: '승인 대기',
  REJECTED: '반려',
  DISABLED: '보류',
};

/**
 * 관리 창에서 바꿀 수 있는 상태는 둘뿐이다.
 *
 * 승인 대기·반려는 가입 신청 단계의 판단이라 「승인」·「반려」 버튼이 맡고,
 * 반려된 계정을 올리는 것은 「복원」이 권한 선택까지 받아 처리한다.
 * 여기서 그것까지 하면 권한을 정하는 판단을 건너뛰게 된다.
 */
const EDITABLE_STATUS = ['APPROVED', 'DISABLED'];

/** 신청 시각. 승인 판단에 쓰이므로 관리 창에서도 보여준다. */
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

export default function UserProfileModal({ user, requireVerify, onClose, onSaved }) {
  const [isEditing, setIsEditing] = useState(false);
  const [form, setForm] = useState({
    name: user.name || '',
    email: user.email || '',
    pwd: '',
  });
  const [status, setStatus] = useState(user.status);
  const [holdReason, setHoldReason] = useState('');
  const canEditStatus = EDITABLE_STATUS.includes(user.status);
  const [showPwd, setShowPwd] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // 계정을 바꾸는 자리이므로 여기서 재확인을 받는다.
  const handleEdit = () => requireVerify(() => setIsEditing(true));

  const handleCancelEdit = () => {
    setForm({ name: user.name || '', email: user.email || '', pwd: '' });
    setStatus(user.status);
    setShowPwd(false);
    setIsEditing(false);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await updateUserByAdmin(user.id, form);

      // 바뀌지 않았으면 부르지 않는다. 매번 승인 API가 나가면 안 된다.
      if (status !== user.status) {
        if (status === 'APPROVED') await approveUser(user.id);
        else if (status === 'DISABLED') await disableUser(user.id, holdReason);
      }

      toast.success('사용자 정보가 수정되었습니다.');
      onSaved();
    } catch (err) {
      toast.error(err.userMessage ?? '수정 중 오류가 발생했습니다.');
      setIsSaving(false);
    }
  };

  const ROW = 'flex px-5 py-3';
  const LABEL = 'w-24 shrink-0 text-xs font-bold text-gray-400 pt-2';
  const INPUT = 'w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]';

  return (
    <div className="absolute inset-0 z-[255] flex items-center justify-center bg-black/40 backdrop-blur-sm rounded-xl">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl relative animate-in fade-in zoom-in-95 duration-200">
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer z-10"
        >
          <span className="material-symbols-outlined">close</span>
        </button>

        {/* 위 - 사람. 사진은 관리자가 바꿀 일이 아니라 보기만 한다. */}
        <div className="p-5 flex items-center gap-5">
          <Avatar src={user.profileImage} userId={user.userId} size={72} />
          <div className="min-w-0 flex-1">
            <p className="font-bold text-gray-900 text-xl truncate">{user.name}</p>
            <p className="text-sm text-gray-500 mt-0.5">
              {user.userId}
              <span className="mx-1.5 text-gray-300">·</span>
              <span className="font-bold text-[#0058be]">{user.role}</span>
            </p>
          </div>
        </div>

        {/* 아래 - 값. 라벨/값 2열을 「내 계정」과 같게 맞춘다. */}
        <div className="border-t border-gray-100 divide-y divide-gray-100">
          <div className={ROW}>
            <span className={LABEL}>이름</span>
            {isEditing ? (
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className={INPUT}
              />
            ) : (
              <span className="text-sm text-gray-800 pt-1.5 break-all">{user.name || '-'}</span>
            )}
          </div>

          <div className={ROW}>
            <span className={LABEL}>이메일</span>
            {isEditing ? (
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className={INPUT}
              />
            ) : (
              <span className="text-sm text-gray-800 pt-1.5 break-all">{user.email || '-'}</span>
            )}
          </div>

          <div className={ROW}>
            <span className={LABEL}>계정 상태</span>
            <div className="w-full">
              {!isEditing || !canEditStatus ? (
                <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold mt-1 ${
                  user.status === 'APPROVED' ? 'bg-green-100 text-green-700'
                    : user.status === 'PENDING' ? 'bg-yellow-100 text-yellow-700 border border-yellow-200'
                    : 'bg-red-100 text-red-700'
                }`}>
                  {STATUS_LABEL[user.status] ?? user.status}
                </span>
              ) : (
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className={`${INPUT} font-bold cursor-pointer`}
              >
                {EDITABLE_STATUS.map((v) => (
                  <option key={v} value={v} disabled={v === user.status} className={v === user.status ? 'text-gray-400' : 'text-gray-900'}>
                    {STATUS_LABEL[v]}
                  </option>
                ))}
              </select>
              )}
              {isEditing && canEditStatus && status !== user.status && (
                <p className="text-[11px] text-[#0058be] font-bold mt-1">
                  저장하면 {STATUS_LABEL[user.status]} → {STATUS_LABEL[status]} 로 바뀝니다.
                </p>
              )}
              {/* 멀쩡히 쓰던 계정을 내리는 것이므로 사유를 남긴다.
                  없으면 나중에 왜 내렸는지 아무도 모른다. */}
              {isEditing && status === 'DISABLED' && user.status !== 'DISABLED' && (
                <>
                  <textarea
                    value={holdReason}
                    onChange={(e) => setHoldReason(e.target.value)}
                    rows={2}
                    maxLength={500}
                    placeholder="보류 사유 — 예) 담당 업무 변경으로 접근 권한 회수"
                    className={`${INPUT} mt-2 resize-none`}
                  />
                  <p className="text-[11px] text-gray-400 mt-1">
                    본인이 로그인을 시도하면 이 사유가 표시됩니다.
                  </p>
                </>
              )}
            </div>
          </div>

          <div className={ROW}>
            <span className={LABEL}>신청일시</span>
            <span className="text-sm text-gray-800 pt-1.5">{fmtDate(user.createdAt)}</span>
          </div>

          {/* 반려·보관 계정에만 값이 있다. 두 상태가 같은 컬럼을 쓰므로
              라벨만 갈라 붙인다. */}
          {user.rejectReason && (
            <div className={ROW}>
              <span className={LABEL}>
                {user.status === 'DISABLED' ? '보류 사유' : '반려 사유'}
              </span>
              <span className="text-sm text-gray-600 pt-1.5 break-all">{user.rejectReason}</span>
            </div>
          )}

          {isEditing && (
          <div className={ROW}>
            <span className={LABEL}>새 비밀번호</span>
            <div className="relative flex items-center w-full">
              <input
                type={showPwd ? 'text' : 'password'}
                value={form.pwd}
                onChange={(e) => setForm({ ...form, pwd: e.target.value })}
                placeholder="변경 시에만 입력"
                autoComplete="new-password"
                className={`${INPUT} pr-10`}
              />
              {form.pwd.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  className="absolute right-2 text-gray-500 hover:text-gray-800 p-1 rounded-md hover:bg-gray-100 transition-colors cursor-pointer"
                >
                  {/* index.css가 .material-symbols-outlined에 FILL·wght를 한 선언으로
                      걸어두므로, 인라인으로 덮을 때 둘을 함께 지정해야 한다. */}
                  <span
                    className="material-symbols-outlined text-[18px]"
                    style={{ fontVariationSettings: "'FILL' 0, 'wght' 200" }}
                  >
                    {showPwd ? 'visibility_off' : 'visibility'}
                  </span>
                </button>
              )}
            </div>
          </div>
          )}
        </div>

        <div className="border-t border-gray-100 px-5 py-3 flex justify-end gap-2">
          {isEditing ? (
            <>
              <button
                onClick={handleCancelEdit}
                className="px-4 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors duration-150 cursor-pointer"
              >
                취소
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="px-4 py-2 text-xs font-bold text-white bg-[#0058be] rounded-lg hover:bg-[#004a9f] transition-colors duration-150 disabled:opacity-70 flex items-center gap-1 cursor-pointer"
              >
                {isSaving && <span className="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>}
                저장
              </button>
            </>
          ) : (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors duration-150 cursor-pointer"
              >
                닫기
              </button>
              <button
                onClick={handleEdit}
                className="px-4 py-2 text-xs font-bold text-white bg-[#0058be] rounded-lg hover:bg-[#004a9f] transition-colors duration-150 flex items-center gap-1 cursor-pointer"
              >
                <span className="material-symbols-outlined text-[16px]">edit</span>
                편집
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
