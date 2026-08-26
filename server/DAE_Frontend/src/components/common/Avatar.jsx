import { getApiBaseUrl } from '../../config';

/**
 * 사용자 프로필 아바타.
 *
 * 프로필 사진이 없으면 "하늘색 배경 + 아이디" 기본 아바타를 그린다.
 * 기본값을 서버에서 이미지 파일로 만들어 두지 않는 이유:
 *  - 계정마다 파일을 생성·보관할 필요가 없다
 *  - 아이디가 바뀌어도 자동으로 따라간다
 *  - 파일 유실로 깨진 이미지가 뜰 일이 없다
 *
 * @param {string|null} src     서버가 준 상대 URL (예: /profile/xxx.png). 없으면 기본 아바타
 * @param {string}      userId  기본 아바타에 표시할 아이디
 * @param {number}      size    px 단위 지름
 */
export default function Avatar({ src, userId = '', size = 40, className = '' }) {
  const label = String(userId).trim();

  // 아이디가 길면 원 밖으로 넘치므로 지름에 맞춰 글자 크기를 줄인다.
  // (4자 이하는 그대로, 길수록 작게)
  const fontSize = Math.max(
    9,
    Math.round(size / Math.max(2.6, label.length * 0.62))
  );

  if (src) {
    return (
      <div
        className={`rounded-full overflow-hidden border border-[#c2c6d6] shrink-0 ${className}`}
        style={{ width: size, height: size }}
      >
        <img
          src={`${getApiBaseUrl()}${src}`}
          alt={label ? `${label} 프로필` : '프로필'}
          className="w-full h-full object-cover"
        />
      </div>
    );
  }

  return (
    <div
      className={`rounded-full border border-[#c2c6d6] shrink-0 flex items-center justify-center
                  bg-sky-400 text-white font-bold tracking-tight select-none overflow-hidden ${className}`}
      style={{ width: size, height: size, fontSize }}
      title={label}
      aria-label={label ? `${label} 프로필` : '프로필'}
    >
      <span className="px-1 truncate">{label || '?'}</span>
    </div>
  );
}
