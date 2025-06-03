import React from 'react';

const BillCard = ({ id, title, description }) => {

  return (
    <div className="flex overflow-hidden flex-col flex-1 shrink p-6 bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow duration-200 basis-0 min-w-64 max-md:max-w-full">
      <div className="flex flex-col h-full">
        <h3 className="text-lg font-bold text-slate-800 leading-tight mb-3 line-clamp-2">
          {title || '의안 제목 없음'}
        </h3>
        <p className="text-sm text-slate-600 leading-relaxed line-clamp-3 flex-1 mb-4">
          {description || '의안 요약이 제공되지 않았습니다.'}
        </p>
        <a
          href={`/bills/${id}`} // id is bill.bill_id from BillList
          className="mt-auto px-4 py-2 text-sm font-medium text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-50 transition-colors duration-200 text-center"
        >
          의안 보기
        </a>
      </div>
    </div>
  );
};

export default BillCard;