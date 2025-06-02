
import React from 'react';
import { Link } from 'react-router-dom';

const BillCard = ({ id, title, date, description, status }) => {
  const formatDate = (dateString) => {
    if (!dateString) return '';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } catch (error) {
      return dateString;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case '가결':
        return 'bg-green-100 text-green-800';
      case '부결':
        return 'bg-red-100 text-red-800';
      case '심의중':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <Link 
      to={`/bills/${id}`}
      className="flex flex-col min-w-[240px] w-[300px] hover:shadow-lg transition-shadow"
    >
      <div className="flex flex-col p-6 w-full bg-white rounded-lg border border-gray-200 border-solid">
        <div className="flex flex-col w-full">
          <div className="flex flex-col w-full">
            <h3 className="text-lg font-semibold leading-7 text-gray-900">
              {title}
            </h3>
            <div className="flex items-center justify-between mt-1">
              <time className="text-sm leading-5 text-gray-500">
                {formatDate(date)}
              </time>
              {status && (
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(status)}`}>
                  {status}
                </span>
              )}
            </div>
          </div>
          {description && (
            <p className="mt-2 text-base leading-6 text-gray-600 line-clamp-3">
              {description}
            </p>
          )}
        </div>
      </div>
    </Link>
  );
};

export default BillCard;
