import React from 'react';

const HeroSection = () => {
  return (
    <section className="flex overflow-hidden flex-col justify-center items-center px-20 py-24 w-full text-center text-black bg-white max-md:px-5 max-md:max-w-full">
      <div className="flex flex-col items-center max-w-4xl">
        <h1 className="text-6xl font-bold leading-tight max-md:text-4xl max-md:leading-10">
          투명한 정치, 
          <br />
          명확한 시선
        </h1>
        <p className="mt-6 text-xl leading-8 text-gray-600 max-w-2xl">
          국회의 모든 활동을 한눈에 보고, 정치인들의 진짜 목소리를 들어보세요.
          데이터로 보는 투명한 정치의 시작입니다.
        </p>
        <div className="flex gap-4 mt-10">
          <a 
            href="#latest-bills"
            className="gap-2 px-8 py-4 text-lg font-medium leading-7 text-white bg-blue-600 rounded-lg border border-blue-600 border-solid hover:bg-blue-700 transition-colors"
          >
            최신 의안 보기
          </a>
          <a 
            href="#about"
            className="gap-2 px-8 py-4 text-lg font-medium leading-7 text-gray-900 bg-white rounded-lg border border-gray-300 border-solid hover:bg-gray-50 transition-colors"
          >
            더 알아보기
          </a>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;