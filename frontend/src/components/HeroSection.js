import React, { useState } from 'react';

const HeroSection = () => {
  const [activeFilter, setActiveFilter] = useState('all');

  return (
    <section className="relative min-h-[600px] bg-gradient-to-b from-white to-gray-50">
      <div className="container mx-auto px-4 py-20">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-5xl font-bold text-gray-900 mb-6">
            모든 의안에 대한 자세한 분석
          </h2>
          <p className="text-xl text-gray-600 mb-8">
            각 의안의 발전 추이와 정당별 입장 변화를 확인해보세요.
          </p>
          <button className="bg-blue-600 text-white px-8 py-3 rounded-lg hover:bg-blue-700 transition-colors mb-12">
            중요 주제 보기
          </button>
          
          <div className="flex justify-center space-x-4">
            <button
              onClick={() => setActiveFilter('all')}
              className={`px-6 py-2 rounded-full transition-colors ${
                activeFilter === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              전체 의안
            </button>
            <button
              onClick={() => setActiveFilter('in-progress')}
              className={`px-6 py-2 rounded-full transition-colors ${
                activeFilter === 'in-progress'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              진행 중
            </button>
            <button
              onClick={() => setActiveFilter('completed')}
              className={`px-6 py-2 rounded-full transition-colors ${
                activeFilter === 'completed'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              완료된
            </button>
          </div>
        </div>
      </div>
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-white to-transparent" />
    </section>
  );
};

export default HeroSection; 