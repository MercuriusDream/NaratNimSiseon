
import React from 'react';
import { Link, useLocation } from 'react-router-dom';

const NavigationHeader = () => {
  const location = useLocation();

  const isActive = (path) => {
    return location.pathname === path;
  };

  return (
    <header className="flex overflow-hidden absolute inset-x-0 top-0 z-10 flex-wrap gap-5 justify-center items-center p-5 w-full h-20 text-black bg-white min-h-20 shadow-[0px_0px_6px_rgba(0,0,0,0.12)] max-md:max-w-full">
      <Link to="/" className="flex items-center gap-3">
        <img
          src="/logo192.png"
          alt="Logo"
          className="object-contain shrink-0 self-stretch my-auto w-10 aspect-square rounded-[100px]"
        />
        <h1 className="text-3xl font-medium leading-none">
          나랏님 시선
        </h1>
      </Link>
      
      <nav className="flex gap-10 justify-center items-center self-stretch my-auto text-base bg-white min-w-60 ml-auto">
        <Link 
          to="/" 
          className={`self-stretch my-auto hover:text-blue-600 transition-colors ${
            isActive('/') ? 'text-blue-600 font-semibold' : ''
          }`}
        >
          홈
        </Link>
        <Link 
          to="/parties" 
          className={`self-stretch my-auto hover:text-blue-600 transition-colors ${
            isActive('/parties') ? 'text-blue-600 font-semibold' : ''
          }`}
        >
          정당 목록
        </Link>
        <Link 
          to="/sessions" 
          className={`self-stretch my-auto hover:text-blue-600 transition-colors ${
            isActive('/sessions') ? 'text-blue-600 font-semibold' : ''
          }`}
        >
          회의록 목록
        </Link>
        <Link 
          to="/bills" 
          className={`self-stretch my-auto hover:text-blue-600 transition-colors ${
            isActive('/bills') ? 'text-blue-600 font-semibold' : ''
          }`}
        >
          의안 목록
        </Link>
      </nav>
    </header>
  );
};

export default NavigationHeader;
