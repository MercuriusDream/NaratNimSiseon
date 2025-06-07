
import React from 'react';

const PartyCard = ({ id, image, title, subtitle, description }) => {
  return (
    <div className="flex overflow-hidden flex-col flex-1 shrink p-6 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow duration-200 basis-0 min-w-64 max-md:max-w-full">
      <div className="flex flex-col items-center text-center">
        <div className="w-16 h-16 rounded-full mb-4 bg-blue-100 flex items-center justify-center">
          <span className="text-blue-600 font-bold text-lg">
            {title ? title.charAt(0) : '정'}
          </span>
        </div>
        <h3 className="text-xl font-bold text-slate-800 mb-2">
          {title}
        </h3>
        {subtitle && (
          <p className="text-sm font-medium text-blue-600 mb-3">
            {subtitle}
          </p>
        )}
        <p className="text-sm text-slate-600 leading-relaxed line-clamp-3">
          {description || '정당 정보가 제공되지 않았습니다.'}
        </p>
        <a
          href={`/parties/${id}`}
          className="mt-4 px-4 py-2 text-sm font-medium text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-50 transition-colors duration-200"
        >
          자세히 보기
        </a>
      </div>
    </div>
  );
};

export default PartyCard;
