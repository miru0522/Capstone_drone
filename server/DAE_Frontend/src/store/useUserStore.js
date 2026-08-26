import { create } from 'zustand';

const useUserStore = create((set) => ({
  userInfo: null, // { userId, name, role, status, ... }
  isAccountModalOpen: false,
  isHistoryOpen: false,

  setUserInfo: (info) => set({ userInfo: info }),
  clearUserInfo: () => set({ userInfo: null }),
  
  openAccountModal: () => set({ isAccountModalOpen: true, isHistoryOpen: false }),
  closeAccountModal: () => set({ isAccountModalOpen: false }),

  openHistory: () => set({ isHistoryOpen: true, isAccountModalOpen: false }),
  closeHistory: () => set({ isHistoryOpen: false }),

  goToDashboard: () => set({ isAccountModalOpen: false, isHistoryOpen: false }),
}));

export default useUserStore;
