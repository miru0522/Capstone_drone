import React, { useState, useEffect } from 'react';
import useDroneStore from '../../store/useDroneStore';
import useUserStore from '../../store/useUserStore';
import { getRoutes, getWaypoints, createRoute, updateRoute, deleteRoute, checkRouteName } from '../../services/api';
import toast from 'react-hot-toast';

/**
 * 순찰 경로(A, B …) 관리.
 * 경로는 팀 공용 자산이며, 순찰 시작 팝업에서 프리셋으로 선택된다.
 * 조회는 전원 가능하고 생성·수정·삭제는 ADMIN만 가능하다.
 * 지점 편집은 지도 그리기 모드로 넘겨서 처리한다.
 */
export default function RouteManagerModal() {
  const isOpen = useDroneStore((state) => state.isRouteManagerOpen);
  const setOpen = useDroneStore((state) => state.setRouteManagerOpen);
  const startEditingRoute = useDroneStore((state) => state.startEditingRoute);
  const setHasUnsavedChanges = useDroneStore((state) => state.setHasUnsavedChanges);
  // 순찰 경로는 팀 공용 자산이다. 조회는 전원, 생성·수정·삭제는 ADMIN만.
  const isAdmin = useUserStore((state) => state.userInfo?.role) === 'ADMIN';

  const [routes, setRoutes] = useState([]);
  const [counts, setCounts] = useState({}); // routeId → 지점 수
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newComment, setNewComment] = useState('');
  // 수정 중인 경로. null이면 목록만 보여준다.
  const [editing, setEditing] = useState(null);

  const load = async () => {
    setIsLoading(true);
    try {
      const list = await getRoutes();
      const rows = Array.isArray(list) ? list : [];
      setRoutes(rows);

      // 지점 수는 경로별로 따로 조회해야 한다. 목록 응답에 개수가 없다.
      const entries = await Promise.all(rows.map(async (w) => {
        try {
          const pts = await getWaypoints(w.routeId);
          return [w.routeId, Array.isArray(pts) ? pts.length : 0];
        } catch {
          return [w.routeId, null];
        }
      }));
      setCounts(Object.fromEntries(entries));
    } catch {
      toast.error('순찰 경로 목록을 불러오지 못했습니다.');
      setRoutes([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      load();
    } else {
      setIsCreating(false);
      setEditing(null);
      setNewName('');
      setNewComment('');
      setHasUnsavedChanges(false);
    }
  }, [isOpen]);

  useEffect(() => {
    if (newName.length > 0 || newComment.length > 0 || isCreating || editing) {
      setHasUnsavedChanges(true);
    } else {
      setHasUnsavedChanges(false);
    }
  }, [newName, newComment, isCreating, editing, setHasUnsavedChanges]);

  if (!isOpen) return null;

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) {
      toast.error('경로 이름을 입력해 주세요.');
      return;
    }
    try {
      // 이름은 전역으로 유일해야 한다. 서버도 막지만, 지도로 넘어간 뒤 실패하면
      // 입력한 내용을 잃으므로 여기서 먼저 걸러 준다.
      if (await checkRouteName(name)) {
        toast.error('이미 있는 경로 이름입니다.');
        return;
      }

      const routeId = await createRoute(name, newComment.trim());
      toast.success(`'${name}' 경로를 만들었습니다. 지도에서 지점을 찍으세요.`);
      setNewName('');
      setNewComment('');
      setIsCreating(false);
      setOpen(false);
      startEditingRoute({ routeId, routeName: name }, []);
    } catch (e) {
      toast.error(e.message || '경로 생성에 실패했습니다.');
    }
  };

  // 수정 폼 열기. 이름·설명은 여기서 바로 고치고, 경로만 지도로 넘어간다.
  const openEdit = (route) => {
    setIsCreating(false);
    setEditing(route);
    setNewName(route.routeName || '');
    setNewComment(route.routeComment || '');
  };

  const handleUpdate = async () => {
    const name = newName.trim();
    if (!name) {
      toast.error('경로 이름을 입력해 주세요.');
      return;
    }
    try {
      await updateRoute(editing.routeId, name, newComment.trim());
      toast.success('경로 정보를 수정했습니다.');
      setEditing(null);
      setNewName('');
      setNewComment('');
      load();
    } catch (e) {
      // 서버가 이름 중복을 400 + 메시지로 돌려준다
      toast.error(e?.response?.data || '경로 수정에 실패했습니다.');
    }
  };

  // 기존 지점을 지도에 미리 띄워 이어서 수정할 수 있게 한다.
  const handleEdit = async (route) => {
    try {
      const pts = await getWaypoints(route.routeId);
      const points = (Array.isArray(pts) ? pts : []).map(p => ({ lat: p.latitude, lng: p.longitude }));
      setOpen(false);
      startEditingRoute(route, points);
      toast('지도에서 경로를 수정하고 "경로 저장"을 누르세요.', { icon: '🗺️' });
    } catch {
      toast.error('경로 지점을 불러오지 못했습니다.');
    }
  };

  const handleDelete = async (route) => {
    if (!window.confirm(`'${route.routeName}' 경로를 삭제할까요?`)) return;
    try {
      await deleteRoute(route.routeId);
      toast.success('경로를 삭제했습니다.');
      load();
    } catch {
      toast.error('경로 삭제에 실패했습니다.');
    }
  };

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl shadow-2xl w-[560px] max-h-[80%] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-3 bg-[#f8f9ff] shrink-0">
          <span className="material-symbols-outlined text-blue-600">route</span>
          <h2 className="text-lg font-bold text-gray-800">순찰 경로 관리</h2>
          <button
            onClick={() => setOpen(false)}
            className="ml-auto p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {isLoading ? (
            <p className="text-sm text-gray-500 text-center py-10">불러오는 중…</p>
          ) : routes.length === 0 ? (
            <div className="text-center py-10 text-gray-500">
              <span className="material-symbols-outlined text-4xl mb-2 block">route</span>
              <p className="text-sm">저장된 순찰 경로가 없습니다.</p>
              {!isAdmin && <p className="text-xs mt-1">경로 등록은 관리자에게 요청하세요.</p>}
            </div>
          ) : (
            <ul className="space-y-2">
              {routes.map((route) => (
                <li
                  key={route.routeId}
                  className="flex items-center gap-3 p-3 border border-[#c2c6d6] rounded-xl hover:bg-[#f8f9ff] transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-sm text-[#0b1c30] truncate">{route.routeName}</p>
                    <p className="text-xs text-[#727785] truncate">
                      {counts[route.routeId] == null ? '지점 정보 없음' : `${counts[route.routeId]}개 지점`}
                      {route.routeComment ? ` · ${route.routeComment}` : ''}
                    </p>
                  </div>
                  {isAdmin && (
                    <>
                      <button
                        onClick={() => openEdit(route)}
                        className="px-3 py-1.5 text-xs font-bold text-[#0058be] bg-white border border-[#c2c6d6] rounded-lg hover:bg-[#e5eeff] transition-colors"
                      >
                        수정
                      </button>
                      <button
                        onClick={() => handleDelete(route)}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        title="삭제"
                      >
                        <span className="material-symbols-outlined text-[18px]">delete</span>
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}

          {isAdmin && editing && (
            <div className="mt-4 p-4 border border-[#a8b8e0] bg-[#f8f9ff] rounded-xl space-y-3">
              <p className="text-xs font-bold text-[#727785] uppercase tracking-wider">경로 수정</p>
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="경로 이름"
                className="w-full p-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
              <input
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="설명 (선택)"
                className="w-full p-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />

              {/* 지점 편집은 지도 클릭이 필요해서 폼 안에서 처리할 수 없다. 지도로 넘어간다. */}
              <div className="flex items-center justify-between pt-1 border-t border-[#c2c6d6]">
                <span className="text-xs text-[#727785]">
                  경로 {counts[editing.routeId] == null ? '- ' : counts[editing.routeId]}개 지점
                </span>
                <button
                  onClick={() => handleEdit(editing)}
                  className="px-3 py-1.5 text-xs font-bold text-[#0058be] bg-white border border-[#c2c6d6] rounded-lg hover:bg-[#e5eeff] flex items-center gap-1"
                >
                  <span className="material-symbols-outlined text-[16px]">route</span>
                  지도에서 경로 편집
                </button>
              </div>

              <div className="flex justify-end gap-2">
                <button
                  onClick={() => { setEditing(null); setNewName(''); setNewComment(''); }}
                  className="px-3 py-1.5 text-xs font-bold text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  취소
                </button>
                <button
                  onClick={handleUpdate}
                  className="px-3 py-1.5 text-xs font-bold text-white bg-blue-600 border border-blue-700 rounded-lg hover:bg-blue-700"
                >
                  저장
                </button>
              </div>
            </div>
          )}

          {isAdmin && isCreating && (
            <div className="mt-4 p-4 border border-[#a8b8e0] bg-[#f8f9ff] rounded-xl space-y-3">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="경로 이름 (예: 외곽 순찰 A)"
                className="w-full p-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
              <input
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="설명 (선택)"
                className="w-full p-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setIsCreating(false)}
                  className="px-3 py-1.5 text-xs font-bold text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  취소
                </button>
                <button
                  onClick={handleCreate}
                  className="px-3 py-1.5 text-xs font-bold text-white bg-blue-600 border border-blue-700 rounded-lg hover:bg-blue-700"
                >
                  만들고 지점 찍기
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="p-4 bg-gray-50 border-t border-gray-100 flex items-center justify-end gap-3 shrink-0">
          {!isAdmin && (
            <p className="mr-auto text-xs text-[#727785] flex items-center gap-1">
              <span className="material-symbols-outlined text-[16px]">lock</span>
              읽기 전용 — 경로 편집은 관리자 권한이 필요합니다.
            </p>
          )}
          <button
            onClick={() => setIsCreating(true)}
            disabled={isCreating || !!editing}
            className={`px-4 py-2 text-sm font-bold text-white bg-blue-600 border border-blue-700 rounded-lg shadow-sm hover:bg-blue-700 disabled:opacity-50 items-center gap-2 ${isAdmin ? 'flex' : 'hidden'}`}
          >
            <span className="material-symbols-outlined text-[18px]">add</span>
            새 경로
          </button>
        </div>
      </div>
    </div>
  );
}
