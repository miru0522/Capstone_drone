import React, { useState } from 'react';
import { approveUser, rejectUser, changeUserRole } from '../../services/api';
import Avatar from '../common/Avatar';
import toast from 'react-hot-toast';
import { parseServerTime } from '../../utils/time';

/**
 * 가입 신청에 대한 판단 창 — 승인과 거절이 한 컴포넌트를 나눠 쓴다.
 *
 * 골격(사람 정보 → 입력 → 버튼)이 같아야 두 창이 어긋나지 않는다. 파일을
 * 나누면 그 골격이 복사되고, 한쪽만 고쳤을 때 서로 달라 보인다.
 * 갈리는 것은 색·아이콘·입력·저장 방식뿐이다.
 *
 * <b>승인</b>: 부여할 권한을 고른다. 기본은 VIEWER — 승인은 "가입 허가"일
 * 뿐이고 드론을 움직일 권한은 별개라는 현재 설계를 따른다(User.onCreate 주석).
 *
 * <b>복원</b>: 승인과 같은 절차다. 보관함에는 반려된 신청도 함께 있어, 그냥
 * 승인 상태로 되돌리면 권한을 정하는 판단을 건너뛰게 된다. 기본값만 다르다 —
 * 그 계정의 현재 권한을 그대로 띄워 보류된 사용자가 강등되지 않게 한다.
 *
 * <b>반려</b>: 사유를 적는다. 본인이 로그인을 시도하면 그 문구가 보인다.
 * 선택 입력이라 비워도 된다.
 */

const ROLE_DESC = {
  VIEWER: '조회만 가능',
  OPERATOR: '드론 조작 · 경보 승인',
  ADMIN: '모든 기능 (계정·드론 관리 포함)',
};

/** 신청 시각. 오래 방치된 건을 먼저 처리하려면 언제 신청했는지 보여야 한다. */
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

export default function UserDecisionModal({ mode, user, onClose, onDone }) {
  const isRestore = mode === 'restore';
  // 복원도 승인과 같은 일을 한다 - 상태를 APPROVED 로 올리고 권한을 정한다.
  const isApprove = mode === 'approve' || isRestore;

  const [role, setRole] = useState(isRestore ? (user.role || 'VIEWER') : 'VIEWER');
  const [reason, setReason] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async () => {
    setIsSaving(true);
    try {
      if (isApprove) {
        await approveUser(user.id);
        // 승인 API는 상태만 바꾼다. 권한은 별도 API다.
        // 값이 그대로면 부르지 않는다.
        if (role !== user.role) await changeUserRole(user.id, role);
      } else {
        await rejectUser(user.id, reason);
      }
      toast.success(isRestore ? '계정을 복원했습니다.' : isApprove ? '가입을 승인했습니다.' : '가입을 반려했습니다.');
      onDone();
    } catch (err) {
      toast.error(err.userMessage ?? (isApprove ? '승인 처리 중 오류가 발생했습니다.' : '반려 처리 중 오류가 발생했습니다.'));
      setIsSaving(false);
    }
  };

  const ROW = 'flex px-5 py-2.5 text-sm';
  const LABEL = 'w-20 shrink-0 text-xs font-bold text-gray-400 pt-0.5';

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

        {/* 제목 — 색과 아이콘만 갈린다 */}
        <div className="flex items-center gap-3 p-5 pb-4">
          <div className={`p-2 rounded-full flex items-center justify-center ${
            isApprove ? 'bg-blue-100 text-[#0058be]' : 'bg-red-100 text-red-600'
          }`}>
            <span className="material-symbols-outlined">
              {isRestore ? 'unarchive' : isApprove ? 'person_add' : 'person_off'}
            </span>
          </div>
          <h2 className="text-xl font-bold text-gray-900">
            {isRestore ? '계정 복원' : isApprove ? '가입 승인' : '가입 반려'}
          </h2>
        </div>

        {/* 사람 — 누구를 판단하는지 */}
        <div className="border-t border-gray-100 px-5 py-4 flex items-center gap-4">
          <Avatar src={user.profileImage} userId={user.userId} size={48} />
          <div className="min-w-0">
            <p className="font-bold text-gray-900 truncate">{user.name}</p>
            <p className="text-xs text-gray-500">{user.userId}</p>
          </div>
        </div>

        <div className="border-t border-gray-100 divide-y divide-gray-100">
          <div className={ROW}>
            <span className={LABEL}>이메일</span>
            <span className="text-gray-800 break-all">{user.email || '-'}</span>
          </div>
          <div className={ROW}>
            <span className={LABEL}>신청일시</span>
            <span className="text-gray-800">{fmtDate(user.createdAt)}</span>
          </div>
          {/* 보관함에서 열었으면 왜 막혔는지 함께 보여준다 - 복원 판단의 근거다. */}
          {isRestore && user.rejectReason && (
            <div className={ROW}>
              <span className={LABEL}>{user.status === 'DISABLED' ? '보류 사유' : '반려 사유'}</span>
              <span className="text-gray-600 break-all">{user.rejectReason}</span>
            </div>
          )}
        </div>

        {/* 입력 — 여기가 두 창의 실제 차이다 */}
        <div className="border-t border-gray-100 p-5">
          {isApprove ? (
            <>
              <p className="text-xs font-bold text-gray-500 mb-2">
                {isRestore ? '복원할 권한' : '부여할 권한'}
              </p>
              <div className="flex flex-col gap-1.5">
                {['VIEWER', 'OPERATOR', 'ADMIN'].map((r) => (
                  <label
                    key={r}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border cursor-pointer transition-colors duration-150 ${
                      role === r ? 'border-[#0058be] bg-[#e5eeff]' : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={r}
                      checked={role === r}
                      onChange={() => setRole(r)}
                      className="accent-[#0058be] cursor-pointer"
                    />
                    <span className="text-sm font-bold text-gray-800 w-[84px]">{r}</span>
                    <span className="text-xs text-gray-500">{ROLE_DESC[r]}</span>
                  </label>
                ))}
              </div>
              {role !== 'VIEWER' && (
                <p className="text-[11px] text-red-600 font-bold bg-red-50 rounded-lg px-2.5 py-2 mt-2.5">
                  {role} 권한은 실제 드론을 움직일 수 있습니다.
                </p>
              )}
            </>
          ) : (
            <>
              <p className="text-xs font-bold text-gray-500 mb-2">반려 사유 <span className="font-normal text-gray-400">(선택)</span></p>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                maxLength={500}
                autoFocus
                placeholder="예) 소속을 확인할 수 없습니다."
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg outline-none resize-none transition-all focus:ring-2 focus:ring-red-100 focus:border-red-400"
              />
              <p className="text-[11px] text-gray-400 mt-1.5">
                본인이 로그인을 시도하면 이 사유가 표시됩니다. 비워 두면 사유 없이 반려 사실만 알립니다.
              </p>
            </>
          )}
        </div>

        <div className="border-t border-gray-100 px-5 py-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-bold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors duration-150 cursor-pointer"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSaving}
            className={`px-4 py-2 text-xs font-bold text-white rounded-lg transition-colors duration-150 disabled:opacity-70 flex items-center gap-1 cursor-pointer ${
              isApprove ? 'bg-[#0058be] hover:bg-[#004a9f]' : 'bg-red-600 hover:bg-red-700'
            }`}
          >
            {isSaving && <span className="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>}
            {isRestore ? '복원' : isApprove ? '승인' : '반려'}
          </button>
        </div>
      </div>
    </div>
  );
}
