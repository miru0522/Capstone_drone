import React, { useState, useEffect, useMemo } from 'react';
import useUserStore from '../../store/useUserStore';
import useDroneStore from '../../store/useDroneStore';
import { getAdminUsers, changeUserRole, deleteUserByAdmin } from '../../services/api';
import UserProfileModal from './UserProfileModal';
import UserDecisionModal from './UserDecisionModal';
import ConfirmDialog from '../common/ConfirmDialog';
import toast from 'react-hot-toast';
import { parseServerTime } from '../../utils/time';

/**
 * 「사용자 관리」 탭 - 남의 계정을 승인/거절/삭제하고 권한을 바꾼다. ADMIN 전용.
 *
 * 내 계정은 MyAccountTab 이 맡는다. 성격이 전혀 다른 두 일을 한 화면에
 * 쌓아두면 스크롤 안에서 서로 방해한다.
 */
/** 하위 탭 ↔ 서버 status 대응 */
/**
 * 탭이 담는 상태들.
 *
 * 보관함은 둘을 함께 담는다 - 가입을 반려한 계정(REJECTED)과 쓰던 계정을
 * 보류한 계정(DISABLED). 둘 다 "지금은 못 쓰지만 지운 것은 아닌" 자리이고,
 * 복원과 제거를 한곳에서 하는 편이 찾기 쉽다.
 */
const SUB_STATUS = {
  users: ['APPROVED'],
  pending: ['PENDING'],
  archived: ['REJECTED', 'DISABLED'],
};

const SUB_TABS = [
  ['users', '사용자'],
  ['pending', '승인 대기'],
  ['archived', '보관함'],
];

/** 사용자 탭 정렬 순서 — 높은 권한부터. 모르는 값은 맨 뒤. */
const ROLE_RANK = { ADMIN: 0, OPERATOR: 1, VIEWER: 2 };

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

const EMPTY_TEXT = {
  users: '승인된 사용자가 없습니다.',
  pending: '승인을 기다리는 신청이 없습니다.',
  archived: '보관함이 비어 있습니다.',
};

/** 보관함에서 왜 여기 있는지 구분해 보여준다. */
const ARCHIVED_LABEL = { REJECTED: '반려', DISABLED: '보류' };

export default function UserAdminTab({ requireVerify }) {
  const { userInfo } = useUserStore();
  const setHasUnsavedChanges = useDroneStore((state) => state.setHasUnsavedChanges);

  const [users, setUsers] = useState([]);
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('ALL');
  // 승인 대기 / 승인된 사용자 / 거절됨 을 갈라 본다. 개수를 탭에 박아
  // 표를 보지 않고도 처리할 건이 있는지 알 수 있게 한다.
  const [subTab, setSubTab] = useState('users');


  // 프로필 관리 창을 띄울 대상. null 이면 닫혀 있다.
  const [profileUser, setProfileUser] = useState(null);
  // 승인/거절 판단 창. { mode: 'approve'|'reject', user } 또는 null.
  const [decision, setDecision] = useState(null);
  // 확인 대화상자. { kind, user, role? } 또는 null.
  const [confirm, setConfirm] = useState(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    setHasUnsavedChanges(Boolean(profileUser));
  }, [profileUser, setHasUnsavedChanges]);

  // 사용자 탭은 높은 권한부터, 같은 권한 안에서는 본인이 먼저 온다.
  const sortedUsers = useMemo(() => {
    if (!Array.isArray(users)) return [];

    // 아이디와 이름 양쪽에서 찾는다. 관제사가 어느 쪽을 기억할지 알 수 없다.
    const q = query.trim().toLowerCase();
    let list = users.filter((u) => {
      const hitQuery = !q
        || String(u.userId || '').toLowerCase().includes(q)
        || String(u.name || '').toLowerCase().includes(q);
      const hitTab = SUB_STATUS[subTab].includes(u.status);
      // 역할 필터는 승인된 사용자에게만 뜻이 있다.
      const hitRole = subTab !== 'users' || roleFilter === 'ALL' || u.role === roleFilter;
      return hitQuery && hitTab && hitRole;
    });

    // 사용자 탭은 높은 권한부터(ADMIN → OPERATOR → VIEWER). 다른 탭은 권한이 뜻이 없다
    // (승인 대기는 전부 기본값, 보관함은 쓰지 않는 계정).
    // 같은 권한 안에서는 본인 계정이 먼저, 나머지는 서버가 준 순서 그대로 —
    // Array.sort 는 안정 정렬이다.
    // (id가 응답마다 있으리라 보장이 없어 본인은 로그인 아이디로 대조한다)
    const me = userInfo?.userId;
    const rank = (u) => ROLE_RANK[u.role] ?? 99;
    return [...list].sort((a, b) =>
      (subTab === 'users' ? rank(a) - rank(b) : 0)
      || (me ? (b.userId === me) - (a.userId === me) : 0));
  }, [users, userInfo?.userId, query, roleFilter, subTab]);

  // 탭에 박을 개수. 검색·필터와 무관하게 전체를 센다.
  const counts = useMemo(() => ({
    pending: users.filter((u) => u.status === 'PENDING').length,
    users: users.filter((u) => u.status === 'APPROVED').length,
    archived: users.filter((u) => u.status === 'REJECTED' || u.status === 'DISABLED').length,
  }), [users]);

  const fetchUsers = async () => {
    try {
      const data = await getAdminUsers();
      setUsers(data);
    } catch (err) {
      toast.error(err.userMessage ?? '사용자 목록을 불러오는 중 오류가 발생했습니다.');
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  // 남의 계정을 바꾸는 동작은 전부 재확인을 받는다.
  // 승인·거절은 확인만으로 끝나지 않는다 - 부여할 권한과 거절 사유를 정해야
  // 하므로 창을 띄운다.
  const openDecision = (mode, user) => requireVerify(() => setDecision({ mode, user }));

  // 보류는 관리 창에서 계정 상태를 바꿔 처리한다. 표에 버튼을 따로 두면
  // 「관리」와 하는 일이 겹친다.

  // 복원은 승인 창을 띄운다. 보관함에는 반려된 신청도 함께 있어,
  // 그냥 승인 상태로 되돌리면 권한을 정하는 판단을 건너뛰게 된다.
  // 기본값은 그 계정의 현재 권한이라 보류된 사용자는 원래 권한이 유지된다.
  const handleRestore = (user) => requireVerify(() => setDecision({ mode: 'restore', user }));

  // 보관함에서만 지운다. 목록에서 바로 지울 수 없게 두 단계로 나눴다.
  const handleDelete = (user) => requireVerify(() => setConfirm({ kind: 'delete', user }));

  const handleRoleChange = (user, newRole) => requireVerify(() => setConfirm({ kind: 'role', user, role: newRole }));

  // 확인을 통과한 뒤 실제로 실행한다. 세 조작이 성공·실패 처리가 같아 한 곳에 모은다.
  const runConfirmed = async () => {
    const { kind, user, role } = confirm;
    setIsBusy(true);
    try {
      if (kind === 'delete') await deleteUserByAdmin(user.id);
      else if (kind === 'role') await changeUserRole(user.id, role);
      setConfirm(null);
      fetchUsers();
    } catch (err) {
      toast.error(err.userMessage ?? '처리 중 오류가 발생했습니다.');
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <>
              <div className="flex-1 flex flex-col overflow-hidden">
                <h3 className="font-bold text-gray-800 mb-3 flex justify-between items-center">
                  <span>사용자 관리</span>
                  {/* 밑줄은 아이콘까지 그어져 지저분하다. 다른 버튼과 같이
                      주변이 밝아지는 방식으로 맞춘다. */}
                  <button
                    onClick={fetchUsers}
                    className="px-2 py-1 rounded-lg text-xs font-bold text-[#0058be] hover:bg-[#e5eeff] transition-colors duration-150 flex items-center gap-1 cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[14px]">refresh</span>새로고침
                  </button>
                </h3>
                {/* 하위 탭 - 개수를 함께 보여준다 */}
                <div className="flex gap-1 mb-3">
                  {SUB_TABS.map(([id, label]) => (
                    <button
                      key={id}
                      onClick={() => setSubTab(id)}
                      className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all duration-150 cursor-pointer flex items-center gap-1.5 ${
                        subTab === id
                          ? 'bg-[#e5eeff] text-[#0058be]'
                          : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                      }`}
                    >
                      {label}
                      <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
                        id === 'pending' && counts.pending > 0
                          ? 'bg-yellow-400 text-white'
                          : 'bg-gray-200 text-gray-600'
                      }`}>
                        {counts[id]}
                      </span>
                    </button>
                  ))}
                </div>

                <div className="flex gap-2 mb-2">
                  <div className="relative flex-1">
                    <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-[18px] pointer-events-none">search</span>
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="아이디 또는 이름"
                      className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg outline-none transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]"
                    />
                  </div>
                  {/* 역할 필터는 승인된 사용자에게만 뜻이 있다.
                      대기·거절 탭에서는 역할이 아직 의미가 없다. */}
                  {subTab === 'users' && (
                    <select
                      value={roleFilter}
                      onChange={(e) => setRoleFilter(e.target.value)}
                      className="px-2 py-2 text-xs font-bold border border-gray-200 rounded-lg outline-none cursor-pointer transition-all focus:ring-2 focus:ring-blue-100 focus:border-[#0058be]"
                    >
                      <option value="ALL">전체 권한</option>
                      <option value="ADMIN">ADMIN</option>
                      <option value="OPERATOR">OPERATOR</option>
                      <option value="VIEWER">VIEWER</option>
                    </select>
                  )}
                </div>
                {/* scrollbar-gutter: stable - 탭마다 행 수가 달라 세로 스크롤바가
                    생기거나 사라지면서 표 폭이 그만큼 달라졌다. 자리를 항상
                    비워 둬 열이 밀리지 않게 한다. */}
                <div className="overflow-y-auto overflow-x-hidden flex-1 bg-gray-50 rounded-lg border border-gray-200 [scrollbar-gutter:stable]">
                  {/* table-fixed + colgroup 으로 열 폭을 못 박는다.
                      기본(auto) 배치는 탭마다 내용 길이가 달라 폭을 다시 계산해,
                      탭을 왔다갔다 하면 표가 흔들린다. */}
                  <table className="w-full table-fixed text-sm text-center">
                    <colgroup>
                      <col className="w-[26%]" />
                      <col className="w-[20%]" />
                      <col className="w-[26%]" />
                      <col className="w-[28%]" />
                    </colgroup>
                    <thead className="bg-gray-100 sticky top-0 text-xs uppercase font-bold text-gray-600">
                      <tr>
                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">아이디</th>
                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">이름</th>
                        {/* 승인 대기·거절 계정은 권한이 전부 VIEWER 다(가입 기본값).
                            보여줄 값이 아니라, 그 자리에 승인 판단에 쓰이는
                            신청일시를 놓는다. */}
                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">
                          {subTab === 'users' ? '권한' : subTab === 'archived' ? '구분' : '신청일시'}
                        </th>

                        <th className="px-2 py-3 border-b border-gray-200 whitespace-nowrap">관리</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedUsers.length === 0 ? (
                        <tr>
                          <td colSpan="4" className="text-center py-8 text-gray-500 font-medium">
                            {query.trim() ? '찾는 조건에 맞는 사용자가 없습니다.' : EMPTY_TEXT[subTab]}
                          </td>
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
                                {subTab === 'users' ? (
                                  <>
                                  {/* 승인된 계정만 권한을 바꿀 수 있다. 다만 바꿀 수 없는 행의 배지가
                                      작으면 열이 들쭉날쭉해 보이므로, 같은 크기의 박스를 유지하고
                                      '조작 불가'만 점선·흐린 색으로 나타낸다. */}
                                  {u.status === 'APPROVED' ? (
                                    /* 본인은 강등할 수 없다. 유일한 ADMIN이 자기를 내리면
                                       관리자 기능에 아무도 접근할 수 없게 된다. */
                                    <select
                                      value={u.role}
                                      onChange={(e) => handleRoleChange(u, e.target.value)}
                                      disabled={isMe}
                                      title={isMe ? '본인 권한은 변경할 수 없습니다' : undefined}
                                      className={`w-[104px] px-2 py-1 rounded text-xs font-bold outline-none border ${isMe ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'} ${u.role === 'ADMIN' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-gray-50 border-gray-200 text-gray-700'}`}
                                    >
                                      {/* 닫힌 상태의 글자색(ADMIN이면 빨강)이 목록 안 항목까지
                                          번지므로 항목마다 색을 되돌린다.
                                          지금 권한은 고를 이유가 없어 잠근다. */}
                                      {['ADMIN', 'OPERATOR', 'VIEWER'].map((r) => (
                                        <option
                                          key={r}
                                          value={r}
                                          disabled={r === u.role}
                                          className={r === u.role ? 'text-gray-400' : 'text-gray-900'}
                                        >
                                          {r}
                                        </option>
                                      ))}
                                    </select>
                                  ) : (
                                    <span
                                      className="inline-block w-[104px] px-2 py-1 rounded text-xs font-bold text-center border border-dashed border-gray-300 bg-gray-50 text-gray-400"
                                      title="승인된 계정만 권한을 변경할 수 있습니다"
                                    >
                                      {u.role}
                                    </span>
                                  )}
                                  </>
                                ) : subTab === 'archived' ? (
                                  <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                                    u.status === 'DISABLED'
                                      ? 'bg-amber-100 text-amber-700'
                                      : 'bg-red-100 text-red-700'
                                  }`}>
                                    {ARCHIVED_LABEL[u.status]}
                                  </span>
                                ) : (
                                  <span className="text-xs text-gray-600">{fmtDate(u.createdAt)}</span>
                                )}
                              </td>
                              <td className="px-2 py-3 text-center whitespace-nowrap">
                                {u.status === 'PENDING' ? (
                                  <div className="flex justify-center gap-1.5">
                                    <button onClick={() => openDecision('approve', u)} className="px-2 py-1 bg-[#0058be] text-white text-xs font-bold rounded hover:bg-[#004a9f] transition-colors duration-150 cursor-pointer">승인</button>
                                    <button onClick={() => openDecision('reject', u)} className="px-2 py-1 bg-red-500 text-white text-xs font-bold rounded hover:bg-red-600 transition-colors duration-150 cursor-pointer">반려</button>
                                  </div>
                                ) : u.status === 'APPROVED' ? (
                                  <div className="flex justify-center gap-1.5">
                                    {/* 상태 변경(승인↔보류)은 관리 창 안에서 한다.
                                        표에 버튼을 따로 두면 「관리」와 하는 일이 겹친다. */}
                                    <button onClick={() => setProfileUser(u)} className="px-2 py-1 bg-gray-200 text-gray-700 text-xs font-bold rounded hover:bg-gray-300 transition-colors duration-150 whitespace-nowrap cursor-pointer">관리</button>
                                  </div>
                                ) : (u.status === 'REJECTED' || u.status === 'DISABLED') ? (
                                  <div className="flex justify-center gap-1.5">
                                    <button onClick={() => setProfileUser(u)} className="px-2 py-1 bg-gray-200 text-gray-700 text-xs font-bold rounded hover:bg-gray-300 transition-colors duration-150 whitespace-nowrap cursor-pointer">관리</button>
                                    <button onClick={() => handleRestore(u)} className="px-2 py-1 bg-[#0058be] text-white text-xs font-bold rounded hover:bg-[#004a9f] transition-colors duration-150 cursor-pointer">복원</button>
                                    <button onClick={() => handleDelete(u)} className="px-2 py-1 bg-red-50 text-red-600 border border-red-200 text-xs font-bold rounded hover:bg-red-100 transition-colors duration-150 cursor-pointer">제거</button>
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

      {profileUser && (
        <UserProfileModal
          user={profileUser}
          requireVerify={requireVerify}
          onClose={() => setProfileUser(null)}
          onSaved={() => { setProfileUser(null); fetchUsers(); }}
        />
      )}

      {confirm?.kind === 'delete' && (
        <ConfirmDialog
          tone="danger"
          icon="person_remove"
          title="계정 제거"
          subtitle={confirm.user.userId}
          requireText={confirm.user.userId}
          confirmLabel="제거"
          isBusy={isBusy}
          onConfirm={runConfirmed}
          onClose={() => setConfirm(null)}
        >
          <p>
            <span className="font-bold">{confirm.user.name}</span>({confirm.user.userId}) 계정과
            그 계정에 남은 기록이 <span className="font-bold">영구히</span> 삭제됩니다.
            <span className="text-red-500 font-bold bg-red-50 px-1 mt-1 inline-block">되돌릴 수 없습니다.</span>
          </p>
        </ConfirmDialog>
      )}

      {confirm?.kind === 'role' && (
        <ConfirmDialog
          tone={confirm.role === 'VIEWER' ? 'primary' : 'warn'}
          icon="admin_panel_settings"
          title="권한 변경"
          subtitle={confirm.user.userId}
          confirmLabel="변경"
          isBusy={isBusy}
          onConfirm={runConfirmed}
          onClose={() => setConfirm(null)}
        >
          <p>
            <span className="font-bold">{confirm.user.name}</span> 의 권한을{' '}
            <span className="font-bold">{confirm.user.role}</span> →{' '}
            <span className="font-bold text-[#0058be]">{confirm.role}</span> 로 바꿉니다.
          </p>
          {confirm.role !== 'VIEWER' && (
            <p className="text-[11px] text-red-600 font-bold bg-red-50 rounded-lg px-2.5 py-2 mt-3">
              {confirm.role} 권한은 실제 드론을 움직일 수 있습니다.
            </p>
          )}
        </ConfirmDialog>
      )}

      {confirm?.kind === 'reapprove' && (
        <ConfirmDialog
          tone="primary"
          icon="how_to_reg"
          title="계정 재승인"
          subtitle={confirm.user.userId}
          confirmLabel="재승인"
          isBusy={isBusy}
          onConfirm={runConfirmed}
          onClose={() => setConfirm(null)}
        >
          <p>
            거절했던 <span className="font-bold">{confirm.user.name}</span> 계정을 다시 승인합니다.
            로그인이 가능해지고 <span className="font-bold">거절 사유는 지워집니다.</span>
            <span className="block text-xs text-gray-500 mt-2">
              권한은 지금 값({confirm.user.role})이 그대로 유지됩니다.
            </span>
          </p>
        </ConfirmDialog>
      )}

      {decision && (
        <UserDecisionModal
          mode={decision.mode}
          user={decision.user}
          onClose={() => setDecision(null)}
          onDone={() => { setDecision(null); fetchUsers(); }}
        />
      )}
    </>
  );
}
