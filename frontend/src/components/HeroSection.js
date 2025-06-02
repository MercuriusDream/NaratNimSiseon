
import React from 'react';

const HeroSection = () => {
  return (
    <section className="flex overflow-hidden flex-col items-center px-20 pt-32 pb-20 w-full bg-gradient-to-b from-blue-50 to-white max-md:px-5 max-md:pt-24 max-md:max-w-full">
      <div className="flex flex-col items-center max-w-4xl text-center">
        <h1 className="text-5xl font-bold text-slate-800 leading-tight max-md:text-4xl max-md:leading-tight mb-6">
          대한민국 국회의 모든 것을
          <br />
          <span className="text-blue-600">한눈에 보세요</span>
        </h1>
        <p className="text-xl text-slate-600 leading-relaxed max-w-2xl mb-8">
          국회 의안, 회의록, 정당 정보를 쉽고 빠르게 찾아보세요.
          투명하고 접근 가능한 정치 정보를 제공합니다.
        </p>
        <div className="flex gap-4 max-md:flex-col max-md:w-full">
          <a
            href="/bills"
            className="px-8 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors duration-200"
          >
            의안 둘러보기
          </a>
          <a
            href="/sessions"
            className="px-8 py-3 border-2 border-blue-600 text-blue-600 font-semibold rounded-lg hover:bg-blue-50 transition-colors duration-200"
          >
            회의록 보기
          </a>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
