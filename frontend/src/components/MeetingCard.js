
import React from 'react';

const MeetingCard = ({ id, title, date, description }) => {
  const formatDate = (dateString) => {
    if (!dateString) return '날짜 미정';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } catch {
      return dateString;
    }
  };

  return (
    <div className="flex overflow-hidden flex-col flex-1 shrink p-6 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow duration-200 basis-0 min-w-64 max-md:max-w-full">
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-2 h-2 bg-green-500 rounded-full"></div>
          <span className="text-sm font-medium text-slate-500">
            {formatDate(date)}
          </span>
        </div>
        <h3 className="text-lg font-bold text-slate-800 leading-tight mb-3 line-clamp-2">
          {title || '회의록 제목 없음'}
        </h3>
        <p className="text-sm text-slate-600 leading-relaxed line-clamp-3 flex-1 mb-4">
          {description || '회의록 요약이 제공되지 않았습니다.'}
        </p>
        <a
          href={`/sessions/${id}`}
          className="mt-auto px-4 py-2 text-sm font-medium text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-50 transition-colors duration-200 text-center"
        >
          회의록 보기
        </a>
      </div>
    </div>
  );
};

export default MeetingCard;
