import React, { useState, useEffect } from 'react';
import { login, registerUser, checkUserId } from '../../services/api';

export default function LoginScreen({ onLoginSuccess }) {
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [id, setId] = useState('');
  const [pwd, setPwd] = useState('');
  const [pwdConfirm, setPwdConfirm] = useState('');   // 회원가입 전용
  const [showPwd, setShowPwd] = useState(false);
  const [name, setName] = useState(''); // 회원가입용
  const [email, setEmail] = useState(''); // 회원가입용 이메일
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // 아이디 중복 상태: null=미확인 / 'checking' / 'taken' / 'free'
  const [idStatus, setIdStatus] = useState(null);

  // 회원가입 중에만, 입력이 멎은 뒤 한 번만 조회한다.
  // 매 타이핑마다 부르면 서버를 두드리게 되므로 400ms 디바운스를 둔다.
  useEffect(() => {
    if (!isRegisterMode || id.trim().length < 2) {
      setIdStatus(null);
      return;
    }
    setIdStatus('checking');
    const timer = setTimeout(async () => {
      try {
        const { exists } = await checkUserId(id.trim());   // 응답은 { exists: boolean }
        setIdStatus(exists ? 'taken' : 'free');
      } catch {
        setIdStatus(null);   // 확인 실패는 조용히 넘긴다. 최종 판단은 서버가 한다.
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [id, isRegisterMode]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      if (isRegisterMode) {
        // 오타가 그대로 계정이 되면 승인까지 기다린 뒤에야 알게 된다. 여기서 막는다.
        if (pwd !== pwdConfirm) {
          setError('비밀번호가 일치하지 않습니다.');
          setIsLoading(false);
          return;
        }
        if (idStatus === 'taken') {
          setError('이미 사용 중인 아이디입니다.');
          setIsLoading(false);
          return;
        }
        // 회원가입
        await registerUser({ userId: id, pwd, name, email });
        alert('가입이 신청되었습니다. 관리자 승인 후 로그인할 수 있으며, 처음에는 조회 권한으로 시작합니다.');
        setIsRegisterMode(false);
        setId('');
        setPwd('');
        setPwdConfirm('');
        setEmail('');
      } else {
        // 로그인
        const res = await login(id, pwd);
        onLoginSuccess();
      }
    } catch (err) {
      console.error(err);
      if (isRegisterMode) {
        setError(err.response?.data?.message ?? '회원가입에 실패했습니다. 잠시 후 다시 시도해주세요.');
      } else {
        if (err.response?.status === 403) {
          setError('승인 대기 중이거나 반려된 계정입니다. 관리자에게 문의해주세요.');
        } else {
          setError('로그인에 실패했습니다. 아이디와 비밀번호를 확인해주세요.');
        }
      }
    } finally {
      setIsLoading(false);
    }
  };

  const toggleMode = () => {
    setIsRegisterMode(!isRegisterMode);
    setError('');
    setId('');
    setPwd('');
    setPwdConfirm('');
    setShowPwd(false);
    setName('');
    setEmail('');
  };

  return (
    <div className="absolute inset-0 z-[1000] flex items-center justify-center bg-[#0b1c30] bg-opacity-95 backdrop-blur-sm">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl p-8 relative animate-in fade-in zoom-in duration-300">
        {/* 로고 첫 등장 시퀀스. 로그인 화면은 처음 그려지는 자리라
            워드마크 와이프까지 그대로 재생해도 어색하지 않다. */}
        <div className="logo-intro flex flex-col items-center mb-8">
          <svg width="48" height="48" viewBox="0 0 120 120" role="img" aria-hidden="true" className="logo-mark mb-4">
            <defs>
              <mask id="loginEyeInv">
                <rect x="0" y="0" width="120" height="120" fill="#FFFFFF"/>
                <polygon points="60,47 73,60 60,73 47,60" fill="#000000"/>
              </mask>
            </defs>
            <g fill="#0058be" mask="url(#loginEyeInv)">
              <rect x="40" y="16" width="40" height="7"/>
              <rect x="40" y="97" width="40" height="7"/>
              <rect x="16" y="40" width="7" height="40"/>
              <rect x="97" y="40" width="7" height="40"/>
              <rect x="51" y="22" width="18" height="76"/>
              <rect x="22" y="51" width="76" height="18"/>
            </g>
            <polygon points="60,54 66,60 60,66 54,60" fill="#0058be"/>
          </svg>
          <h2 className="logo-word text-2xl font-black tracking-tighter text-gray-900">A.D.D 관제 시스템</h2>
          {/* 로고 원본(add_logo_v1_inverted.html)의 태그라인. A.D.D가 무엇의 약자인지 밝힌다. */}
          <p
            className="logo-sub mt-1.5 text-[11px] font-medium text-gray-400 uppercase"
            style={{ letterSpacing: '1.5px' }}
          >
            Anomaly&nbsp;·&nbsp;Detection&nbsp;·&nbsp;Drone
          </p>
          <p className="logo-sub text-sm text-gray-500 mt-3 font-medium">
            {isRegisterMode ? '가입 후 관리자 승인을 받으면 이용할 수 있습니다' : '계정 정보를 입력해 주세요'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-1">아이디</label>
            <input 
              type="text" 
              value={id}
              onChange={(e) => setId(e.target.value)}
              className={`w-full px-4 py-2 border rounded-lg focus:ring-2 outline-none transition-all ${
                isRegisterMode && idStatus === 'taken'
                  ? 'border-red-400 focus:ring-red-500/30 focus:border-red-500'
                  : 'border-gray-300 focus:ring-[#0058be] focus:border-[#0058be]'
              }`}
              placeholder="아이디를 입력하세요"
              required
            />
            {isRegisterMode && idStatus && (
              <p className={`text-xs mt-1 ${
                idStatus === 'taken' ? 'text-red-500 font-semibold'
                  : idStatus === 'free' ? 'text-green-600 font-semibold' : 'text-gray-400'
              }`}>
                {idStatus === 'checking' ? '확인 중…'
                  : idStatus === 'taken' ? '이미 사용 중인 아이디입니다.'
                  : '사용할 수 있는 아이디입니다.'}
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-1">비밀번호</label>
            <div className="relative flex items-center">
              <input
                type={showPwd ? 'text' : 'password'}
                value={pwd}
                onChange={(e) => setPwd(e.target.value)}
                className="w-full px-4 py-2 pr-11 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#0058be] focus:border-[#0058be] outline-none transition-all"
                placeholder="비밀번호를 입력하세요"
                autoComplete={isRegisterMode ? 'new-password' : 'current-password'}
                required
              />
              {pwd.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  className="absolute right-3 text-gray-500 hover:text-gray-800 focus:outline-none flex items-center justify-center p-1 rounded-md hover:bg-gray-100 transition-colors"
                >
                  {/* 계정 관리 화면과 같은 얇은 선(wght 200).
                      index.css가 FILL·wght·GRAD·opsz를 한 선언으로 걸어두므로 FILL도 함께 적는다. */}
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

          {isRegisterMode && (
            <div>
              <label className="block text-sm font-bold text-gray-700 mb-1">비밀번호 확인</label>
              <input
                type={showPwd ? 'text' : 'password'}
                value={pwdConfirm}
                onChange={(e) => setPwdConfirm(e.target.value)}
                className={`w-full px-4 py-2 border rounded-lg outline-none transition-all focus:ring-2 ${
                  pwdConfirm.length > 0 && pwd !== pwdConfirm
                    ? 'border-red-400 focus:ring-red-200 focus:border-red-400'
                    : 'border-gray-300 focus:ring-[#0058be] focus:border-[#0058be]'
                }`}
                placeholder="비밀번호를 다시 입력하세요"
                autoComplete="new-password"
                required
              />
              {pwdConfirm.length > 0 && (
                <p className={`mt-1 text-xs font-medium flex items-center gap-1 ${
                  pwd === pwdConfirm ? 'text-green-600' : 'text-red-500'
                }`}>
                  <span className="material-symbols-outlined text-[14px]">
                    {pwd === pwdConfirm ? 'check_circle' : 'error'}
                  </span>
                  {pwd === pwdConfirm ? '비밀번호가 일치합니다.' : '비밀번호가 일치하지 않습니다.'}
                </p>
              )}
            </div>
          )}
          {isRegisterMode && (
            <>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-1">이름 (담당자명)</label>
                <input 
                  type="text" 
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#0058be] focus:border-[#0058be] outline-none transition-all"
                  placeholder="이름을 입력하세요"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-1">이메일</label>
                <input 
                  type="email" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#0058be] focus:border-[#0058be] outline-none transition-all"
                  placeholder="이메일을 입력하세요"
                  required
                />
              </div>
            </>
          )}
          
          {error && (
            <p className="text-red-500 text-sm font-bold bg-red-50 p-2 rounded-md border border-red-100 flex items-center gap-1">
              <span className="material-symbols-outlined text-[16px]">error</span>
              {error}
            </p>
          )}

          <button 
            type="submit" 
            disabled={isLoading}
            className="w-full py-2.5 bg-[#0058be] hover:bg-[#004a9f] text-white font-bold rounded-lg shadow-md transition-colors disabled:opacity-70 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <span className="material-symbols-outlined animate-spin text-[20px]">progress_activity</span>
            ) : (
              <span className="material-symbols-outlined text-[20px]">{isRegisterMode ? 'person_add' : 'login'}</span>
            )}
            {isRegisterMode ? '가입 신청하기' : '로그인'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600">
            {isRegisterMode ? '이미 계정이 있으신가요?' : '계정이 없으신가요?'}
            <button 
              onClick={toggleMode} 
              type="button"
              className="text-[#0058be] font-bold hover:underline ml-1"
            >
              {isRegisterMode ? '로그인으로 돌아가기' : '회원가입'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
