/**
 * 드론 제어 버튼. 색과 크기를 한 곳에서 관리해 카드마다 클래스가 흩어지지 않게 한다.
 *
 * @param {string}   icon     material-symbols 아이콘 이름
 * @param {string}   tone     default | primary | warn | neutral | land | home | danger
 * @param {boolean}  disabled 비활성 (신호 없는 드론 등)
 * @param {boolean}  full     한 줄 전체를 차지할지
 */
const TONES = {
  default: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-100',
  primary: 'bg-blue-600 text-white border-blue-700 hover:bg-blue-700',
  warn:    'bg-yellow-50 text-yellow-700 border-yellow-200 hover:bg-yellow-100',
  neutral: 'bg-gray-100 text-gray-700 border-gray-300 hover:bg-gray-200',
  land:    'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100',
  home:    'bg-orange-50 text-orange-600 border-orange-200 hover:bg-orange-100',
  danger:  'bg-gray-50 text-red-600 border-red-200 hover:bg-red-50',
};

export default function ControlButton({
  icon, label, onClick, tone = 'default', disabled = false, full = false,
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();   // 카드 자체의 접힘/펼침 토글과 겹치지 않게 한다
        if (!disabled) onClick?.(e);
      }}
      disabled={disabled}
      className={`${full ? 'col-span-2' : ''} w-full py-2 rounded-lg border text-xs font-bold shadow-sm
                  transition-colors flex items-center justify-center gap-1
                  disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-inherit
                  ${TONES[tone] ?? TONES.default}`}
    >
      <span className="material-symbols-outlined text-[14px]">{icon}</span>
      {label}
    </button>
  );
}
