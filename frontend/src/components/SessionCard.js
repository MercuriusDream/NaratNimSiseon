import React from 'react';
import { Link } from 'react-router-dom';

const SessionCard = ({ session }) => {
  return (
    <div className="bg-white overflow-hidden shadow rounded-lg">
      <div className="px-4 py-5 sm:p-6">
        <div className="flex items-center">
          <div className="flex-shrink-0 bg-indigo-500 rounded-md p-3">
            <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
          <div className="ml-5 w-0 flex-1">
            <dl>
              <dt className="text-sm font-medium text-gray-500 truncate">
                {session.era_co} {session.sess} {session.dgr}
              </dt>
              <dd>
                <div className="text-lg font-medium text-gray-900">
                  {new Date(session.conf_dt).toLocaleDateString('ko-KR')}
                </div>
              </dd>
            </dl>
          </div>
        </div>
      </div>
      <div className="bg-gray-50 px-4 py-4 sm:px-6">
        <div className="text-sm">
          <Link
            to={`/sessions/${session.conf_id}`}
            className="font-medium text-indigo-600 hover:text-indigo-500"
          >
            상세보기
          </Link>
        </div>
      </div>
    </div>
  );
};

export default SessionCard; 