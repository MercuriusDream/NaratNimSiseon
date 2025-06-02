import React from 'react';

const Footer = () => {
  return (
    <footer className="flex overflow-hidden z-0 gap-10 justify-center items-center p-16 w-full text-xl leading-7 text-center text-black max-md:px-5 max-md:max-w-full">
      <nav className="flex flex-wrap gap-10 justify-center self-stretch my-auto min-h-[100px] min-w-60 max-md:max-w-full">
        <a href="#" className="w-[74px]">이용약관</a>
        <a href="#" className="w-[153px]">개인정보 처리방침</a>
        <a href="#" className="w-[74px]">문의하기</a>
        <a href="#" className="w-[139px]">소셜 미디어 링크</a>
      </nav>
    </footer>
  );
};

export default Footer; 