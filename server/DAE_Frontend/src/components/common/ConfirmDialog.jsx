import React, { useState } from 'react';

/**
 * 확인 대화상자.
 *
 * 브라우저 기본 `window.confirm` 을 대체한다. 기본 창은 회색 OS 상자라
 * 디자인이 통째로 깨지고, 무엇보다 <b>경고의 무게가 전달되지 않는다</b> —
 * 계정을 영구 삭제하는 것과 페이지를 떠나는 것이 같은 모양으로 보인다.
 *
 * 화면을 멈추는 것 자체는 유지한다. 되돌릴 수 없는 조작 앞에서는 관제사를
 * 멈춰 세우는 것이 맞다(알림은 toast 로 옮겼지만 확인은 그렇지 않다).
 *
 * ⚠️ `fixed` 로 화면 전체를 덮는다. 호출하는 곳마다 부모가 달라(계정 카드,
 *    경로 관리 창, 이력 패널) `absolute` 를 쓰면 덮는 범위가 제각각이 된다.
 *    z-[280] — 계정 창(200)·관리 창(255)·비밀번호 확인(260) 위, 로그인(1000) 아래.
 */

const TONES = {
  danger: {
    ring: 'bg-red-100 text-red-600',
    button: 'bg-red-600 hover:bg-red-700',
    focus: 'focus:ring-red-100 focus:border-red-400',
  },
  warn: {
    ring: 'bg-amber-100 text-amber-600',
    button: 'bg-amber-600 hover:bg-amber-700',
    focus: 'focus:ring-amber-100 focus:border-amber-400',
  },
  primary: {
    ring: 'bg-blue-100 text-[#0058be]',
    button: 'bg-[#0058be] hover:bg-[#004a9f]',
    focus: 'focus:ring-blue-100 focus:border-[#0058be]',
  },
};

export default function ConfirmDialog({
  tone = 'primary',
  icon = 'help',
  title,
  subtitle,
  children,
  /** 이 문자열을 그대로 입력해야 확인 버튼이 열린다. 되돌릴 수 없는 조작에만 쓴다. */
  requireText,
  /** 값을 주면 사유 입력칸이 생긴다. onConfirm 이 그 값을 인자로 받는다. */
  reasonLabel,
  reasonPlaceholder,
  reasonHint,
  confirmLabel = '확인',
  cancelLabel = '취소',
  isBusy = false,
  onConfirm,
  onClose,
}) {
  const [typed, setTyped] = useState('');
  const [reason, setReason] = useState('');
  const t = TONES[tone] ?? TONES.primary;
  const locked = Boolean(requireText) && typed.trim() !== requireText;

  return (
    <div className="fixed inset-0 z-[280] flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white w-full max-w-sm rounded-2xl shadow-2xl p-6 relative animate-in fade-in zoom-in-95 duration-200">
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined">close</span>
        </button>

        <div className="flex items-center gap-3 mb-2">
          <div className={`p-2 rounded-full flex items-center justify-center ${t.ring}`}>
            <span className="material-symbols-outlined">{icon}</span>
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-bold text-gray-900">{title}</h2>
            {subtitle && <p className="text-xs text-gray-500 font-medium truncate">{subtitle}</p>}
          </div>
        </div>

        <hr className="my-4 border-gray-200" />

        <div className="text-sm text-gray-700 leading-relaxed">{children}</div>

        {reasonLabel && (
          <div className="mt-4">
            <label className="block text-xs font-bold text-gray-500 mb-1">
              {reasonLabel} <span className="font-normal text-gray-400">(선택)</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              maxLength={500}
              autoFocus
              placeholder={reasonPlaceholder}
              className={`w-full px-3 py-2 text-sm border border-gray-300 rounded-lg outline-none resize-none transition-all ${t.focus}`}
            />
            {reasonHint && <p className="text-[11px] text-gray-400 mt-1.5">{reasonHint}</p>}
          </div>
        )}

        {requireText && (
          <div className="mt-4">
            <label className="block text-xs font-bold text-gray-500 mb-1">
              계속하려면 <span className="text-gray-900">{requireText}</span> 를 입력하세요
            </label>
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus={!reasonLabel}
              autoComplete="off"
              placeholder={requireText}
              className={`w-full px-3 py-2 text-sm border border-gray-300 rounded-lg outline-none transition-all ${t.focus}`}
            />
          </div>
        )}

        <div className="flex gap-3 justify-end mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-50 border border-gray-200 hover:bg-gray-100 transition-colors duration-150 cursor-pointer"
          >
            {cancelLabel}
          </button>
          <button
            onClick={() => onConfirm(reason)}
            disabled={locked || isBusy}
            className={`px-4 py-2 rounded-lg text-sm font-medium text-white shadow-sm transition-colors duration-150 flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer ${t.button}`}
          >
            {isBusy && <span className="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
