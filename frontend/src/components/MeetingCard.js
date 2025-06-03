
import React from 'react';

// Props are assumed to be passed from a Session object:
// id: session.conf_id
// cmit_nm: session.cmit_nm (위원회명)
// conf_knd: session.conf_knd (회의종류)
// conf_dt: session.conf_dt (회의일자)
// description prop is removed as Session model has no summary/description
const MeetingCard = ({ id, cmit_nm, conf_knd, conf_dt }) => {
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
      return dateString; // Return original string if formatting fails
    }
  };

  // Construct title from cmit_nm and conf_knd
  const meetingTitle = [cmit_nm, conf_knd].filter(Boolean).join(' - ') || '회의 정보 없음';

  return (
    <div className="flex overflow-hidden flex-col flex-1 shrink p-6 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow duration-200 basis-0 min-w-64 max-md:max-w-full">
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-2 h-2 bg-green-500 rounded-full"></div>
          <span className="text-sm font-medium text-slate-500">
            {formatDate(conf_dt)} {/* Use conf_dt for date */}
          </span>
        </div>
        <h3 className="text-lg font-bold text-slate-800 leading-tight mb-3 line-clamp-2">
          {meetingTitle} {/* Use constructed title */}
        </h3>
        <p className="text-sm text-slate-600 leading-relaxed line-clamp-3 flex-1 mb-4">
          {/* Description removed as Session model has no summary. Placeholder can be used if desired. */}
          회의록 요약 정보는 제공되지 않습니다.
        </p>
        <a
          href={`/sessions/${id}`} // id is session.conf_id
          className="mt-auto px-4 py-2 text-sm font-medium text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-50 transition-colors duration-200 text-center"
        >
          회의록 보기
        </a>
      </div>
    </div>
  );
};

export default MeetingCard;
