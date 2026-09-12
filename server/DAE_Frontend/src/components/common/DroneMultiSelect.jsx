import { useEffect, useRef, useState } from 'react';
import { droneColor } from '../../utils/droneColor';

/**
 * 드론 여러 대 고르기.
 *
 * value: null 이면 전체(새로 등록한 드론도 저절로 들어간다), 아니면 고른 드론 id 배열.
 *
 * 창 안에서 누르는 것은 임시 선택이고 「적용」을 눌러야 바뀐다 — 체크박스를 누를 때마다
 * 다시 조회하면 여러 대를 고르는 동안 요청이 여러 번 나간다(비행은 드론 수만큼).
 * 「취소」·바깥 누르기·Esc 는 임시 선택을 버린다. Period 선택기와 같은 방식이다.
 */
export default function DroneMultiSelect({ drones, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(null);   // 창을 연 동안의 임시 선택 (value 와 같은 형식)
  const rootRef = useRef(null);

  const ids = drones.map((d) => d.id);
  // 지워진 드론이 선택에 남아 있어도 보이지 않게 거른다
  const pick = (v) => (v === null ? ids : v.filter((id) => ids.includes(id)));

  const applied = pick(value);               // 버튼에 보이는 것은 적용된 선택
  const appliedAll = ids.length > 0 && applied.length === ids.length;
  const working = pick(open ? draft : value); // 창 안에 보이는 것은 임시 선택
  const workingAll = ids.length > 0 && working.length === ids.length;

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const openPicker = () => {
    setDraft(value);
    setOpen(true);
  };

  // 전부 고르면 「전체」(null)로 둔다 — 그래야 나중에 등록한 드론도 들어간다
  const normalize = (list) => (list.length === ids.length ? null : list);

  const toggle = (id) => {
    const next = working.includes(id) ? working.filter((x) => x !== id) : [...working, id];
    setDraft(normalize(next));
  };

  const apply = () => {
    onChange(draft);
    setOpen(false);
  };

  const label = drones.length === 0
    ? '등록된 드론 없음'
    : appliedAll
      ? '모든 드론'
      : applied.length === 0
        ? '선택 안 함'
        : applied.length === 1
          ? applied[0]
          : `드론 ${applied.length}/${ids.length}`;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : openPicker())}
        disabled={drones.length === 0}
        // 폭을 고정한다 — 「모든 드론」↔「드론 2/3」처럼 글자가 바뀌어도 옆의 기간·버튼이 밀리지 않게.
        className="w-[172px] flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white hover:bg-gray-50 cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:text-gray-400"
      >
        {/* 적용된 드론 색을 겹쳐 보여준다 */}
        <span className="flex -space-x-1 shrink-0">
          {applied.slice(0, 4).map((id) => (
            <span
              key={id}
              className="w-2.5 h-2.5 rounded-full ring-2 ring-white"
              style={{ backgroundColor: droneColor(id) }}
            />
          ))}
        </span>
        <span className={`flex-1 min-w-0 truncate text-left font-medium ${applied.length === 0 ? 'text-red-600' : 'text-gray-800'}`}>
          {label}
        </span>
        <span className="material-symbols-outlined text-[18px] text-gray-400 shrink-0">{open ? 'expand_less' : 'expand_more'}</span>
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-2 z-50 w-64 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
          {/* 버튼 하나로 오간다. 모두 골라져 있으면 「전체 해제」, 아니면 「전체 선택」 —
              체크박스로 일부만 바꿨을 때는 누르면 전부 골라지는 쪽이 자연스럽다. */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100 bg-gray-50/60">
            <span className="text-xs text-gray-500">{working.length}/{ids.length} 선택</span>
            <button
              type="button"
              onClick={() => setDraft(workingAll ? [] : null)}
              className={`px-2 py-1 rounded-md text-xs font-bold cursor-pointer transition-colors ${
                workingAll ? 'text-gray-600 hover:bg-gray-100' : 'text-[#0058be] hover:bg-[#e5eeff]'
              }`}
            >
              {workingAll ? '전체 해제' : '전체 선택'}
            </button>
          </div>

          <ul className="max-h-64 overflow-y-auto py-1">
            {drones.map((d) => {
              const checked = working.includes(d.id);
              return (
                <li key={d.id}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={checked}
                    onClick={() => toggle(d.id)}
                    className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-gray-50 cursor-pointer transition-colors"
                  >
                    <span
                      className={`w-4 h-4 shrink-0 rounded flex items-center justify-center border transition-colors ${
                        checked ? 'bg-[#0058be] border-[#0058be]' : 'bg-white border-gray-300'
                      }`}
                    >
                      {checked && <span className="material-symbols-outlined text-[14px] text-white leading-none">check</span>}
                    </span>
                    <span className="w-2.5 h-2.5 shrink-0 rounded-full" style={{ backgroundColor: droneColor(d.id) }} />
                    <span className="min-w-0 flex-1 truncate text-sm">
                      <span className="font-mono font-medium text-gray-900">{d.id}</span>
                      {d.name && <span className="ml-1.5 text-gray-500">{d.name}</span>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          {/* Period 선택기와 같은 자리·모양 — 오른쪽 아래 [취소][적용] */}
          <div className="px-3 py-2.5 border-t border-gray-100 flex items-center justify-between gap-2">
            <span className={`text-xs truncate ${working.length === 0 ? 'text-red-600' : 'text-gray-500'}`}>
              {working.length === 0 ? '하나 이상 선택하세요' : ''}
            </span>
            <div className="flex gap-2 shrink-0">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="px-3 py-1.5 rounded-lg text-xs font-bold text-gray-600 hover:bg-gray-100 cursor-pointer"
              >
                취소
              </button>
              <button
                type="button"
                onClick={apply}
                disabled={working.length === 0}
                className="px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-[#0058be] hover:bg-[#00479b] cursor-pointer disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                적용
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
