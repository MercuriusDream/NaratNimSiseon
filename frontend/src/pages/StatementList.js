
import React, { useState } from 'react';
import NavigationHeader from '../components/NavigationHeader';
import Footer from '../components/Footer';
import StatementList from '../components/StatementList';
import DataRefreshButton from '../components/DataRefreshButton';

const StatementListPage = () => {
  const [filters, setFilters] = useState({});
  const [refreshKey, setRefreshKey] = useState(0);

  const handleFilterChange = (newFilters) => {
    setFilters(newFilters);
  };

  const handleRefreshComplete = () => {
    setRefreshKey(prev => prev + 1);
  };

  return (
    <div className="relative pt-20 bg-gray-50 min-h-screen">
      <NavigationHeader />
      
      <main className="container mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">국회 발언 분석</h1>
          <p className="text-gray-600">
            국회의원들의 발언을 감성 분석과 함께 확인할 수 있습니다.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          <div className="lg:col-span-3">
            <StatementList key={refreshKey} filters={filters} />
          </div>
          
          <div className="lg:col-span-1">
            <div className="space-y-6">
              <DataRefreshButton onRefreshComplete={handleRefreshComplete} />
              
              {/* Filter Panel */}
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">필터</h3>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      감성 점수 범위
                    </label>
                    <div className="flex space-x-2">
                      <input
                        type="number"
                        min="-1"
                        max="1"
                        step="0.1"
                        placeholder="최소"
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        onChange={(e) => handleFilterChange({
                          ...filters,
                          sentiment_min: e.target.value
                        })}
                      />
                      <input
                        type="number"
                        min="-1"
                        max="1"
                        step="0.1"
                        placeholder="최대"
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        onChange={(e) => handleFilterChange({
                          ...filters,
                          sentiment_max: e.target.value
                        })}
                      />
                    </div>
                  </div>
                  
                  <button
                    onClick={() => setFilters({})}
                    className="w-full px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
                  >
                    필터 초기화
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
      
      <Footer />
    </div>
  );
};

export default StatementListPage;
