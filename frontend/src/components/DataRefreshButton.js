
import React, { useState } from 'react';
import api from '../api';

const DataRefreshButton = ({ onRefreshStart, onRefreshComplete }) => {
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);

  const handleRefresh = async (force = false) => {
    try {
      setRefreshing(true);
      if (onRefreshStart) onRefreshStart();

      const response = await api.post('/api/data/refresh/', { 
        force: force,
        debug: false 
      });

      console.log('Refresh response:', response.data);
      setLastRefresh(new Date());
      
      if (onRefreshComplete) onRefreshComplete();
      
      alert('데이터 갱신이 시작되었습니다. 완료까지 시간이 걸릴 수 있습니다.');
    } catch (error) {
      console.error('Error refreshing data:', error);
      alert('데이터 갱신 중 오류가 발생했습니다.');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">데이터 관리</h3>
      
      <div className="space-y-4">
        <div className="flex space-x-3">
          <button
            onClick={() => handleRefresh(false)}
            disabled={refreshing}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {refreshing && (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
            )}
            최신 데이터 가져오기
          </button>
          
          <button
            onClick={() => handleRefresh(true)}
            disabled={refreshing}
            className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {refreshing && (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
            )}
            전체 데이터 갱신
          </button>
        </div>
        
        {lastRefresh && (
          <p className="text-sm text-gray-600">
            마지막 갱신: {lastRefresh.toLocaleString()}
          </p>
        )}
        
        <div className="text-sm text-gray-500">
          <p>• 최신 데이터 가져오기: 새로운 세션과 의안만 수집</p>
          <p>• 전체 데이터 갱신: 모든 데이터를 다시 수집 (시간이 오래 걸림)</p>
        </div>
      </div>
    </div>
  );
};

export default DataRefreshButton;
