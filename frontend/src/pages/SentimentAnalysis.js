
import React from 'react';
import SentimentDashboard from '../components/SentimentDashboard';

const SentimentAnalysis = () => {
  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">감성 분석 대시보드</h1>
          <p className="mt-2 text-gray-600">
            국회 발언의 감성 분석 결과를 종합적으로 확인할 수 있습니다.
          </p>
        </div>
        
        <SentimentDashboard />
      </div>
    </div>
  );
};

export default SentimentAnalysis;
