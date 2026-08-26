import React, { useEffect, useState } from 'react';
import useDroneStore from '../../store/useDroneStore';
import { getUserDroneSettings, updateUserDroneSettings } from '../../services/api';
import toast from 'react-hot-toast';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
  useDroppable,
} from '@dnd-kit/core';

import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

const Item = ({ content, isOverlay }) => {
  return (
    <div
      className={`p-3 bg-white border rounded-lg shadow-sm flex items-center justify-between transition-all duration-200 ${
        isOverlay ? 'cursor-grabbing ring-2 ring-blue-500 shadow-xl opacity-90' : 'cursor-grab border-gray-200 mb-2'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-gray-400">drag_indicator</span>
        <span className="font-mono font-bold text-gray-700">{content}</span>
      </div>
    </div>
  );
};

const SortableItem = ({ id, content }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition: transition || 'transform 250ms ease',
    opacity: isDragging ? 0.3 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <Item content={content} isOverlay={false} />
    </div>
  );
};

const DroppableContainer = ({ id, items, title, bgColor }) => {
  const { setNodeRef } = useDroppable({ id });
  return (
    <div ref={setNodeRef} className={`p-4 rounded-xl ${bgColor} flex-1 flex flex-col`}>
      <h3 className="text-sm font-bold text-gray-700 mb-3">{title}</h3>
      <SortableContext id={id} items={items.map(i => i.droneId)} strategy={verticalListSortingStrategy}>
        <div className="flex-1 overflow-y-auto min-h-[150px] p-1 -m-1">
          {items.map((item) => (
            <SortableItem key={item.droneId} id={item.droneId} content={item.droneId} />
          ))}
          {items.length === 0 && (
            <div className="h-full flex items-center justify-center border-2 border-dashed border-gray-300 rounded-lg opacity-50">
              <span className="text-xs font-medium">비어 있음</span>
            </div>
          )}
        </div>
      </SortableContext>
    </div>
  );
};

export default function DroneManagementModal() {
  const isOpen = useDroneStore((state) => state.isDroneManagementOpen);
  const setOpen = useDroneStore((state) => state.setDroneManagementOpen);
  const registeredDrones = useDroneStore((state) => state.drones);

  const [visibleItems, setVisibleItems] = useState([]);
  const [hiddenItems, setHiddenItems] = useState([]);
  const [activeId, setActiveId] = useState(null);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );



  useEffect(() => {
    if (isOpen) {
      fetchSettings();
    }
  }, [isOpen]);

  const fetchSettings = async () => {
    try {
      const res = await getUserDroneSettings();
      const dbSettings = Array.isArray(res) ? res : [];
      // DB 설정에 없는 등록된 드론들도 처리
      const allDroneIds = registeredDrones.map(d => d.id);
      
      const v = [];
      const h = [];
      
      // DB에 있는 것부터 분류
      dbSettings.sort((a, b) => a.sortOrder - b.sortOrder).forEach(s => {
        if (s.visible) v.push(s);
        else h.push(s);
      });
      
      // DB에 없는 건 일단 visible에 추가
      allDroneIds.forEach(id => {
        if (!dbSettings.find(s => s.droneId === id)) {
          v.push({ droneId: id, visible: true, sortOrder: 999 });
        }
      });
      
      setVisibleItems(v);
      setHiddenItems(h);
    } catch (e) {
      console.error(e);
      // 에러시 전부 visible
      setVisibleItems(registeredDrones.map(d => ({ droneId: d.id, visible: true, sortOrder: 0 })));
      setHiddenItems([]);
    }
  };

  const handleDragStart = (event) => {
    setActiveId(event.active.id);
  };

  const handleDragCancel = () => {
    setActiveId(null);
  };

  const handleDragOver = (event) => {
    const { active, over } = event;
    if (!over) return;
    
    const activeId = active.id;
    const overId = over.id;
    const activeContainer = findContainer(activeId);
    const overContainer = findContainer(overId) || over.id;

    if (!activeContainer || !overContainer || activeContainer === overContainer) {
      return;
    }

    const sourceItems = activeContainer === 'visible' ? visibleItems : hiddenItems;
    const setSource = activeContainer === 'visible' ? setVisibleItems : setHiddenItems;
    const destItems = overContainer === 'visible' ? visibleItems : hiddenItems;
    const setDest = overContainer === 'visible' ? setVisibleItems : setHiddenItems;

    const activeItem = sourceItems.find(item => item.droneId === activeId);
    const newSource = sourceItems.filter(item => item.droneId !== activeId);
    activeItem.visible = overContainer === 'visible';

    let newDest = [...destItems];
    if (over.id === overContainer) {
      newDest.push(activeItem);
    } else {
      const destIndex = destItems.findIndex(item => item.droneId === overId);
      const isBelowOverItem = over && active.rect.current.translated && active.rect.current.translated.top > over.rect.top + over.rect.height;
      const modifier = isBelowOverItem ? 1 : 0;
      newDest.splice(destIndex >= 0 ? destIndex + modifier : newDest.length + 1, 0, activeItem);
    }

    setSource(newSource);
    setDest(newDest);
  };

  const handleDragEnd = (event) => {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;

    const activeId = active.id;
    const overId = over.id;
    const activeContainer = findContainer(activeId);
    const overContainer = findContainer(overId) || over.id;

    if (activeContainer && activeContainer === overContainer) {
      const items = activeContainer === 'visible' ? visibleItems : hiddenItems;
      const setItems = activeContainer === 'visible' ? setVisibleItems : setHiddenItems;
      const oldIndex = items.findIndex(item => item.droneId === activeId);
      const newIndex = items.findIndex(item => item.droneId === overId);
      if (oldIndex !== newIndex) {
        setItems(arrayMove(items, oldIndex, newIndex));
      }
    }
  };

  const findContainer = (id) => {
    if (id === 'visible' || id === 'hidden') return id;
    if (visibleItems.find(item => item.droneId === id)) return 'visible';
    if (hiddenItems.find(item => item.droneId === id)) return 'hidden';
    return null;
  };

  const handleSave = async () => {
    const payload = [];
    visibleItems.forEach((item, index) => {
      payload.push({ droneId: item.droneId, visible: true, sortOrder: index });
    });
    hiddenItems.forEach((item, index) => {
      payload.push({ droneId: item.droneId, visible: false, sortOrder: index });
    });

    try {
      await updateUserDroneSettings(payload);
      toast.success('사이드바 드론 표시 설정이 저장되었습니다.');
      // 전역 스토어 업데이트 (Sidebar가 새로 그리도록)
      useDroneStore.getState().setDroneSettings(payload);
      setOpen(false);
    } catch (e) {
      toast.error('설정 저장 실패');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-[400px] h-[700px] flex flex-col overflow-hidden animate-in fade-in duration-200">
        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-[#f8f9ff]">
          <h2 className="text-lg font-bold text-[#0058be] flex items-center gap-2">
            <span className="material-symbols-outlined">tune</span>
            사이드바 구성
          </h2>
          <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="flex-1 p-6 flex flex-col gap-4 overflow-hidden">
          <p className="text-sm text-gray-600 mb-2">드래그 앤 드롭으로 사이드바에 표시할 드론과 순서를 설정하세요.</p>
          
          <DndContext 
            sensors={sensors} 
            collisionDetection={closestCenter} 
            onDragStart={handleDragStart}
            onDragOver={handleDragOver} 
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            <div className="flex flex-col gap-4 h-full">
              <DroppableContainer id="visible" items={visibleItems} title="표시 박스 (Visible)" bgColor="bg-blue-50/50 border border-blue-100" />
              <DroppableContainer id="hidden" items={hiddenItems} title="비표시 박스 (Hidden)" bgColor="bg-gray-50/50 border border-gray-200" />
            </div>
            <DragOverlay dropAnimation={{ duration: 250, easing: 'cubic-bezier(0.18, 0.67, 0.6, 1.22)' }}>
              {activeId ? <Item content={activeId} isOverlay={true} /> : null}
            </DragOverlay>
          </DndContext>
        </div>

        <div className="p-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-2">
          <button onClick={() => setOpen(false)} className="px-4 py-2 text-sm font-bold text-gray-600 bg-white border border-gray-300 rounded-lg shadow-sm hover:bg-gray-50">
            취소
          </button>
          <button onClick={handleSave} className="px-4 py-2 text-sm font-bold text-white bg-blue-600 rounded-lg shadow-sm hover:bg-blue-700 flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">save</span>
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
