
import React from 'react';

const Footer = () => {
  return (
    <footer className="flex overflow-hidden flex-col px-20 py-16 w-full bg-slate-900 text-white max-md:px-5 max-md:py-12 max-md:max-w-full">
      <div className="flex flex-col w-full max-w-6xl mx-auto">
        <div className="flex flex-wrap gap-12 justify-between max-md:gap-8">
          <div className="flex flex-col max-w-md">
            <h3 className="text-2xl font-bold mb-4">나랏님 시선</h3>
            <p className="text-slate-300 leading-relaxed mb-6">
              대한민국 국회의 투명성을 높이고, 시민들이 정치에 더 쉽게 접근할 수 있도록 돕는 플랫폼입니다.
            </p>
            <div className="flex gap-4">
              <a href="#" className="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center hover:bg-slate-600 transition-colors">
                <span className="sr-only">Facebook</span>
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                </svg>
              </a>
              <a href="#" className="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center hover:bg-slate-600 transition-colors">
                <span className="sr-only">Twitter</span>
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z"/>
                </svg>
              </a>
            </div>
          </div>
          <div className="flex flex-col">
            <h4 className="text-lg font-semibold mb-4">빠른 링크</h4>
            <ul className="space-y-2 text-slate-300">
              <li><a href="/" className="hover:text-white transition-colors">홈</a></li>
              <li><a href="/bills" className="hover:text-white transition-colors">의안 목록</a></li>
              <li><a href="/sessions" className="hover:text-white transition-colors">회의록 목록</a></li>
              <li><a href="/parties" className="hover:text-white transition-colors">정당 목록</a></li>
            </ul>
          </div>
          <div className="flex flex-col">
            <h4 className="text-lg font-semibold mb-4">정보</h4>
            <ul className="space-y-2 text-slate-300">
              <li><a href="#" className="hover:text-white transition-colors">소개</a></li>
              <li><a href="#" className="hover:text-white transition-colors">이용약관</a></li>
              <li><a href="#" className="hover:text-white transition-colors">개인정보처리방침</a></li>
              <li><a href="#" className="hover:text-white transition-colors">문의하기</a></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-slate-700 pt-8 mt-12">
          <div className="flex flex-wrap justify-between items-center gap-4">
            <p className="text-slate-400">
              © 2024 나랏님 시선. All rights reserved.
            </p>
            <p className="text-slate-400 text-sm">
              데이터 출처: 국회 의안정보시스템
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
