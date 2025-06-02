
import React from 'react';
import { Link } from 'react-router-dom';

const Footer = () => {
  return (
    <footer className="flex overflow-hidden z-0 gap-10 justify-center items-center p-16 w-full text-xl leading-7 text-center text-black bg-gray-50 max-md:px-5 max-md:max-w-full">
      <nav className="flex flex-wrap gap-10 justify-center self-stretch my-auto min-h-[100px] min-w-60 max-md:max-w-full">
        <Link to="/terms" className="hover:text-blue-600 transition-colors">
          이용약관
        </Link>
        <Link to="/privacy" className="hover:text-blue-600 transition-colors">
          개인정보 처리방침
        </Link>
        <Link to="/contact" className="hover:text-blue-600 transition-colors">
          문의하기
        </Link>
        <Link to="/social" className="hover:text-blue-600 transition-colors">
          소셜 미디어 링크
        </Link>
      </nav>
    </footer>
  );
};

export default Footer;
